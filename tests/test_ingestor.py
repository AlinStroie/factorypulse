"""Teste pentru ingestor: parsare, loturi, ordinea scriere -> ack si configurare."""

import json
import queue
from datetime import UTC, datetime
from typing import Any

import pytest
from paho.mqtt.client import MQTTMessage

from factorypulse.bridge.mapping import payload_for
from factorypulse.ingestor.batch import Batch, Reading, Received, parse
from factorypulse.ingestor.ingestor import Ingestor, IngestorConfig, make_mqtt_client

WHEN = datetime(2026, 10, 21, 8, 0, 0, tzinfo=UTC)
INGESTED = datetime(2026, 10, 21, 8, 0, 1, tzinfo=UTC)


def _msg(mid: int, payload: str | None = None) -> Received:
    body = payload if payload is not None else payload_for("motor", "temperatura", 65.0, "C", WHEN)
    return Received(body.encode(), mid, 1, INGESTED)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeWriter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.batches: list[list[Reading]] = []

    def write(self, readings: list[Reading]) -> None:
        if self.fail:
            raise ConnectionError("baza indisponibila")
        self.batches.append(list(readings))


class FakeAcker:
    def __init__(self) -> None:
        self.acked: list[int] = []

    def ack(self, mid: int, qos: int) -> Any:
        self.acked.append(mid)


def _ingestor(
    inbox: "queue.Queue[Received]", writer: FakeWriter, acker: FakeAcker, size: int = 3
) -> tuple[Ingestor, FakeClock]:
    clock = FakeClock()
    return Ingestor(inbox, writer, acker, Batch(size, 1.0), clock), clock


# --- parsare -------------------------------------------------------------------------------


def test_parse_reads_bridge_payload() -> None:
    reading = parse(_msg(1))
    assert reading == Reading("motor", "temperatura", WHEN, 65.0, "C", INGESTED)


@pytest.mark.parametrize(
    "payload",
    [
        "nu e json",
        json.dumps({"machine": "motor", "sensor": "t", "value": 1.0, "unit": "C"}),
        json.dumps({"machine": "m", "sensor": "s", "ts": "ieri", "value": 1.0, "unit": "C"}),
        json.dumps(
            {"machine": "m", "sensor": "s", "ts": WHEN.isoformat(), "value": "x", "unit": "C"}
        ),
        json.dumps(
            {"machine": "m", "sensor": "s", "ts": "2026-10-21T08:00:00", "value": 1, "unit": "C"}
        ),
        json.dumps([1, 2, 3]),
    ],
    ids=["json", "fara-ts", "ts-invalid", "valoare-text", "ts-fara-fus", "nu-e-obiect"],
)
def test_parse_rejects_bad_payloads(payload: str) -> None:
    with pytest.raises(ValueError, match="payload invalid"):
        parse(_msg(1, payload))


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


def test_invalid_message_is_acked_but_not_written() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer, acker = FakeWriter(), FakeAcker()
    ingestor, _ = _ingestor(inbox, writer, acker, size=2)
    inbox.put(_msg(1, "nu e json"))
    inbox.put(_msg(2))
    ingestor.step()
    assert ingestor.step() == 1
    assert [r.machine for r in writer.batches[0]] == ["motor"]
    assert acker.acked == [1, 2]


# --- MQTT si configurare -------------------------------------------------------------------


def test_on_message_only_queues() -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    client = make_mqtt_client(IngestorConfig(), inbox)
    msg = MQTTMessage(mid=7, topic=b"factory/motor/temperatura")
    msg.payload = b"{}"
    msg.qos = 1
    client.on_message(client, None, msg)  # type: ignore[misc]
    received = inbox.get_nowait()
    assert (received.mid, received.qos, received.payload) == (7, 1, b"{}")
    assert received.ingestion_ts.tzinfo is not None


def test_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_HOST", "emqx")
    monkeypatch.setenv("POSTGRES_HOST", "timescaledb")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("INGEST_BATCH_SIZE", "50")
    config = IngestorConfig.from_env()
    assert (config.mqtt_host, config.pg_host, config.batch_size) == ("emqx", "timescaledb", 50)
    assert "password=secret" in config.conninfo()


def test_conninfo_without_password() -> None:
    conninfo = IngestorConfig(pg_password=None).conninfo()
    assert "password" not in conninfo
    assert "dbname=factorypulse" in conninfo
