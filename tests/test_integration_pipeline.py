"""Test cap-coada: MQTT -> ingestor -> bronze + TimescaleDB (telemetrie si carantina).

Ingestorul real (`run`) ruleaza intr-un thread, pe EMQX si TimescaleDB reale. Topicurile,
client_id-ul si schema Postgres au un prefix propriu, ca testul sa poata rula langa stack-ul
live fara sa se amestece cu el.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt
import psycopg
import pyarrow.parquet as pq
import pytest
from paho.mqtt.enums import CallbackAPIVersion
from psycopg.conninfo import conninfo_to_dict

from factorypulse.bridge.mapping import payload_for
from factorypulse.ingestor.ingestor import IngestorConfig, run

pytestmark = pytest.mark.integration

PREFIX = f"fp-test-{os.getpid()}"


def _wait_until(condition: Callable[[], bool], timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.2)
    raise AssertionError(f"conditia nu s-a indeplinit in {timeout_s} s")


@pytest.fixture
def mqtt_address() -> tuple[str, int]:
    address = os.getenv("FP_TEST_MQTT")
    if not address:
        pytest.skip("FP_TEST_MQTT nu e setat")
    host, _, port = address.partition(":")
    return host, int(port or "1883")


@pytest.fixture
def config(pg_conninfo: str, mqtt_address: tuple[str, int], tmp_path: Path) -> IngestorConfig:
    pg = conninfo_to_dict(pg_conninfo)
    return IngestorConfig(
        mqtt_host=mqtt_address[0],
        mqtt_port=mqtt_address[1],
        mqtt_client_id=f"{PREFIX}-ingestor",
        mqtt_topic=f"{PREFIX}/#",
        pg_host=str(pg.get("host", "127.0.0.1")),
        pg_port=int(str(pg.get("port", 5432))),
        pg_user=str(pg["user"]),
        pg_password=str(pg["password"]) if pg.get("password") else None,
        pg_db=str(pg["dbname"]),
        pg_options=str(pg["options"]),
        batch_wait_s=0.2,
        bronze_dir=tmp_path / "bronze",
    )


@pytest.fixture
def publisher(mqtt_address: tuple[str, int]) -> Iterator[Callable[[str, str], None]]:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"{PREFIX}-publisher")
    client.connect(*mqtt_address)
    client.loop_start()

    def publish(sensor: str, payload: str) -> None:
        client.publish(f"{PREFIX}/motor/{sensor}", payload, qos=1).wait_for_publish(timeout=5)

    yield publish
    client.loop_stop()
    client.disconnect()


class RunningIngestor:
    def __init__(self, config: IngestorConfig) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=run, args=(config, self._stop), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=10)
        assert not self._thread.is_alive(), "ingestorul nu s-a oprit"


def _count(conninfo: str, table: str, where: str = "true") -> int:
    """Numara randurile din `table` (calificat cu schema); 0 daca tabelul nu exista inca.

    Ingestorul creeaza tabelele abia la prima scriere, iar un nume necalificat ar putea
    gasi tabelul din `public` al stack-ului live.
    """
    with psycopg.connect(conninfo) as conn:
        exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL", (table,)).fetchone()
        if not (exists and exists[0]):
            return 0
        row = conn.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()
    assert row is not None and isinstance(row[0], int)
    return row[0]


def _bronze_rows(root: Path, sensor_prefix: str) -> int:
    files = list(root.rglob("*.parquet"))
    if not files:
        return 0
    topics = [t for f in files for t in pq.read_table(f).column("topic").to_pylist()]
    return sum(1 for t in topics if t.startswith(f"{PREFIX}/motor/{sensor_prefix}"))


def test_pipeline_end_to_end(
    config: IngestorConfig,
    pg_conninfo: str,
    pg_schema: str,
    publisher: Callable[[str, str], None],
) -> None:
    telemetry, quarantine = f"{pg_schema}.telemetry", f"{pg_schema}.quarantine"
    ingestor = RunningIngestor(config)
    try:
        # Abonarea e asincrona: publicam un mesaj de proba pana cand ajunge in baza.
        probe = payload_for("motor", "proba", 1.0, "C", datetime.now(UTC))

        def probe_arrived() -> bool:
            publisher("proba", probe)
            return _count(pg_conninfo, telemetry) > 0

        _wait_until(probe_arrived)

        now = datetime.now(UTC)
        valid = [
            payload_for("motor", f"s{i % 4}", 60.0 + i, "C", now + timedelta(milliseconds=i))
            for i in range(20)
        ]
        stale = json.loads(valid[0])
        stale["schema_version"] = 2
        invalid = [
            "nu e json",
            payload_for("motor", "s0", -273.0, "C", now),
            json.dumps(stale),
        ]
        for payload in valid:
            publisher("s", payload)
        for payload in valid[:5]:  # retrimise
            publisher("s", payload)
        for payload in invalid:
            publisher("s", payload)

        valid_rows = "sensor LIKE 's_'"
        _wait_until(lambda: _count(pg_conninfo, telemetry, valid_rows) == 20)
        _wait_until(lambda: _count(pg_conninfo, quarantine) == 3)
        _wait_until(lambda: _bronze_rows(config.bronze_dir, "s") == 28)
        with psycopg.connect(pg_conninfo) as conn:
            reasons = sorted(r for (r,) in conn.execute(f"SELECT reason FROM {quarantine}"))
        assert reasons == ["in_afara_limitelor", "payload_invalid", "versiune_nesuportata"]
    finally:
        ingestor.stop()

    # Repornire cu acelasi client_id: daca ack-urile nu ar fi fost trimise, brokerul ar
    # retrimite mesajele, iar bronze (fara deduplicare) ar avea randuri noi.
    bronze_before = _bronze_rows(config.bronze_dir, "")
    restarted = RunningIngestor(config)
    try:
        time.sleep(3)
    finally:
        restarted.stop()
    assert _bronze_rows(config.bronze_dir, "") == bronze_before
    assert _count(pg_conninfo, telemetry, valid_rows) == 20


@pytest.fixture(autouse=True)
def _forget_mqtt_session(mqtt_address: tuple[str, int]) -> Iterator[None]:
    """La final sterge sesiunea persistenta a ingestorului de test din broker."""
    yield
    client = mqtt.Client(
        CallbackAPIVersion.VERSION2, client_id=f"{PREFIX}-ingestor", clean_session=True
    )
    client.connect(*mqtt_address)
    client.disconnect()
