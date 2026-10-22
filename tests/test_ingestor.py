"""Teste pentru ingestor: parsare, loturi, ordinea scriere -> ack si configurare."""

import queue
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from paho.mqtt.client import MQTTMessage

from factorypulse.bridge.mapping import payload_for
from factorypulse.ingestor.batch import Batch, Reading, Received
from factorypulse.ingestor.db import MIGRATIONS, WriteResult, pending_migrations
from factorypulse.ingestor.ingestor import Ingestor, IngestorConfig, make_mqtt_client
from factorypulse.ingestor.validate import Rejected

WHEN = datetime(2026, 10, 21, 8, 0, 0, tzinfo=UTC)
INGESTED = datetime(2026, 10, 21, 8, 0, 1, tzinfo=UTC)


def _msg(mid: int, payload: str | None = None) -> Received:
    # ts diferit per mid, ca mesajele sa nu fie duplicate unele ale altora
    when = WHEN + timedelta(seconds=mid)
    body = payload if payload is not None else payload_for("motor", "temperatura", 65.0, "C", when)
    return Received("factory/motor/temperatura", body.encode(), mid, 1, INGESTED)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeWriter:
    """Imita cheia unica din FP-202: un rand cu aceeasi (masina, senzor, ts) nu se rescrie."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.batches: list[list[Reading]] = []
        self.keys: set[tuple[str, str, datetime]] = set()
        self.quarantine: list[Rejected] = []

    def write(self, readings: list[Reading], rejected: list[Rejected]) -> WriteResult:
        if self.fail:
            raise ConnectionError("baza indisponibila")
        self.batches.append(list(readings))
        self.quarantine.extend(rejected)
        new = {(r.machine, r.sensor, r.ts) for r in readings} - self.keys
        self.keys |= new
        return WriteResult(len(new), len(rejected))


class FakeAcker:
    def __init__(self) -> None:
        self.acked: list[int] = []

    def ack(self, mid: int, qos: int) -> Any:
        self.acked.append(mid)


class FakeBronze:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.batches: list[list[int]] = []
        self.compactions: list[datetime] = []

    def write(self, items: Sequence[Received]) -> Any:
        if self.fail:
            raise OSError("disc plin")
        self.batches.append([m.mid for m in items])

    def compact(self, before: datetime) -> int:
        self.compactions.append(before)
        return 0


class FakeWallClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 21, 10, 30, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def _ingestor(
    inbox: "queue.Queue[Received]",
    writer: FakeWriter,
    acker: FakeAcker,
    size: int = 3,
    bronze: FakeBronze | None = None,
    wall: FakeWallClock | None = None,
) -> tuple[Ingestor, FakeClock]:
    clock = FakeClock()
    ingestor = Ingestor(
        inbox,
        bronze or FakeBronze(),
        writer,
        acker,
        Batch(size, 1.0),
        clock,
        wall or FakeWallClock(),
    )
    return ingestor, clock


# --- lot -----------------------------------------------------------------------------------


def test_batch_is_due_when_full() -> None:
    batch = Batch(max_size=2, max_wait_s=10.0)
    batch.add(_msg(1), now=0.0)
    assert not batch.is_due(now=0.0)
    batch.add(_msg(2), now=0.0)
    assert batch.is_due(now=0.0)


def test_batch_is_due_after_wait_from_first_message() -> None:
    batch = Batch(max_size=100, max_wait_s=1.0)
    assert not batch.is_due(now=50.0)
    assert batch.seconds_left(now=50.0) == 1.0
    batch.add(_msg(1), now=10.0)
    batch.add(_msg(2), now=10.8)
    assert batch.seconds_left(now=10.8) == pytest.approx(0.2)
    assert not batch.is_due(now=10.9)
    assert batch.is_due(now=11.0)


def test_take_empties_batch() -> None:
    batch = Batch(max_size=2, max_wait_s=1.0)
    batch.add(_msg(1), now=0.0)
    assert [m.mid for m in batch.take()] == [1]
    assert batch.items == []
    assert not batch.is_due(now=99.0)


# --- bucla principala ----------------------------------------------------------------------


def test_full_batch_is_written_then_acked() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker = FakeWriter(), FakeAcker()
    ingestor, _ = _ingestor(inbox, writer, acker, size=2)
    inbox.put(_msg(1))
    inbox.put(_msg(2))
    assert ingestor.step() == 0
    assert ingestor.step() == 2
    assert len(writer.batches) == 1 and len(writer.batches[0]) == 2
    assert acker.acked == [1, 2]


def test_partial_batch_is_written_after_wait() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker = FakeWriter(), FakeAcker()
    ingestor, clock = _ingestor(inbox, writer, acker, size=100)
    inbox.put(_msg(1))
    assert ingestor.step() == 0
    clock.now = 1.0
    assert ingestor.step() == 1  # coada e goala, dar a trecut timpul lotului
    assert acker.acked == [1]


def test_nothing_is_acked_when_write_fails() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker = FakeWriter(fail=True), FakeAcker()
    ingestor, _ = _ingestor(inbox, writer, acker, size=1)
    inbox.put(_msg(1))
    with pytest.raises(ConnectionError):
        ingestor.step()
    assert acker.acked == []

    # Baza revine: acelasi lot se scrie la urmatorul pas, fara sa se piarda.
    writer.fail = False
    assert ingestor.step() == 1
    assert acker.acked == [1]


def test_invalid_message_goes_to_quarantine_and_is_acked() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker = FakeWriter(), FakeAcker()
    ingestor, _ = _ingestor(inbox, writer, acker, size=3)
    inbox.put(_msg(1, "nu e json"))
    inbox.put(_msg(2))
    inbox.put(_msg(3, payload_for("motor", "temperatura", -273.0, "C", WHEN)))
    ingestor.step()
    ingestor.step()
    assert ingestor.step() == 1
    assert [r.machine for r in writer.batches[0]] == ["motor"]
    assert [(r.message.mid, r.reason) for r in writer.quarantine] == [
        (1, "payload_invalid"),
        (3, "in_afara_limitelor"),
    ]
    assert acker.acked == [1, 2, 3]


def test_redelivered_batch_is_acked_without_new_rows() -> None:
    # Ingestorul a scris lotul, dar a cazut inainte de ack: brokerul il retrimite.
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker = FakeWriter(), FakeAcker()
    ingestor, _ = _ingestor(inbox, writer, acker, size=1)
    payload = payload_for("motor", "temperatura", 65.0, "C", WHEN)
    inbox.put(_msg(1, payload))
    assert ingestor.step() == 1
    inbox.put(_msg(2, payload))  # acelasi payload, mid nou de la broker
    assert ingestor.step() == 0
    assert acker.acked == [1, 2]
    assert len(writer.keys) == 1


def test_bronze_gets_whole_batch_before_database() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker, bronze = FakeWriter(), FakeAcker(), FakeBronze()
    ingestor, _ = _ingestor(inbox, writer, acker, size=2, bronze=bronze)
    inbox.put(_msg(1, "nu e json"))
    inbox.put(_msg(2))
    ingestor.step()
    ingestor.step()
    assert bronze.batches == [[1, 2]]  # si mesajul invalid
    assert len(writer.batches[0]) == 1


def test_nothing_reaches_database_when_bronze_fails() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker, bronze = FakeWriter(), FakeAcker(), FakeBronze(fail=True)
    ingestor, _ = _ingestor(inbox, writer, acker, size=1, bronze=bronze)
    inbox.put(_msg(1))
    with pytest.raises(OSError):
        ingestor.step()
    assert writer.batches == [] and acker.acked == []


def test_bronze_is_not_rewritten_when_database_retry() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker, bronze = FakeWriter(fail=True), FakeAcker(), FakeBronze()
    ingestor, _ = _ingestor(inbox, writer, acker, size=1, bronze=bronze)
    inbox.put(_msg(1))
    with pytest.raises(ConnectionError):
        ingestor.step()
    writer.fail = False
    assert ingestor.step() == 1
    assert bronze.batches == [[1]]
    assert acker.acked == [1]


def test_compaction_runs_at_start_and_once_per_hour() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    bronze, wall = FakeBronze(), FakeWallClock()
    ingestor, _ = _ingestor(inbox, FakeWriter(), FakeAcker(), bronze=bronze, wall=wall)
    ingestor.step()
    ingestor.step()
    wall.now = datetime(2026, 10, 21, 11, 0, 30, tzinfo=UTC)  # in perioada de gratie
    ingestor.step()
    wall.now = datetime(2026, 10, 21, 11, 1, 0, tzinfo=UTC)
    ingestor.step()
    assert bronze.compactions == [
        datetime(2026, 10, 21, 10, tzinfo=UTC),
        datetime(2026, 10, 21, 11, tzinfo=UTC),
    ]


def test_failed_compaction_does_not_stop_ingestion() -> None:
    class BrokenBronze(FakeBronze):
        def compact(self, before: datetime) -> int:
            raise OSError("fisier blocat")

    inbox: queue.Queue[Received] = queue.Queue()
    acker = FakeAcker()
    ingestor, _ = _ingestor(inbox, FakeWriter(), acker, size=1, bronze=BrokenBronze())
    inbox.put(_msg(1))
    assert ingestor.step() == 1
    assert acker.acked == [1]


# --- MQTT si configurare -------------------------------------------------------------------


def test_on_message_only_queues() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    client = make_mqtt_client(IngestorConfig(), inbox)
    msg = MQTTMessage(mid=7, topic=b"factory/motor/temperatura")
    msg.payload = b"{}"
    msg.qos = 1
    client.on_message(client, None, msg)  # type: ignore[misc]
    received = inbox.get_nowait()
    assert (received.topic, received.mid, received.qos, received.payload) == (
        "factory/motor/temperatura",
        7,
        1,
        b"{}",
    )
    assert received.ingestion_ts.tzinfo is not None


def test_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_HOST", "emqx")
    monkeypatch.setenv("POSTGRES_HOST", "timescaledb")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("INGEST_BATCH_SIZE", "50")
    monkeypatch.setenv("BRONZE_DIR", "/date/bronze")
    config = IngestorConfig.from_env()
    assert config.bronze_dir.as_posix() == "/date/bronze"
    assert (config.mqtt_host, config.pg_host, config.batch_size) == ("emqx", "timescaledb", 50)
    assert "password=secret" in config.conninfo()


def test_conninfo_without_password() -> None:
    conninfo = IngestorConfig(pg_password=None).conninfo()
    assert "password" not in conninfo
    assert "dbname=factorypulse" in conninfo


# --- migrari -------------------------------------------------------------------------------


def test_migrations_are_numbered_in_order() -> None:
    versions = [v for v, _ in MIGRATIONS]
    assert versions == list(range(1, len(MIGRATIONS) + 1))


def test_pending_migrations_skips_applied() -> None:
    assert [v for v, _ in pending_migrations({1})] == [2, 3]
    assert pending_migrations({v for v, _ in MIGRATIONS}) == []
