"""Teste pe un TimescaleDB real (marcate `integration`, vezi tests/conftest.py).

Fiecare test lucreaza intr-o schema proprie, stearsa la final, deci nu atinge datele live.
"""

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from factorypulse.ingestor.batch import Reading, Received
from factorypulse.ingestor.db import MIGRATIONS, PostgresWriter, WriteResult, migrate
from factorypulse.ingestor.validate import Rejected

pytestmark = pytest.mark.integration

WHEN = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)


def _readings(n: int) -> list[Reading]:
    return [
        Reading("motor", "t", WHEN + timedelta(seconds=i), float(i), "C", WHEN) for i in range(n)
    ]


@pytest.fixture
def conninfo(pg_conninfo: str) -> str:
    return pg_conninfo


def _count(conninfo: str) -> object:
    with psycopg.connect(conninfo) as conn:
        row = conn.execute("SELECT count(*) FROM telemetry").fetchone()
    assert row is not None
    return row[0]


def test_reprocessing_does_not_create_duplicates(conninfo: str) -> None:
    writer = PostgresWriter(conninfo)
    try:
        assert writer.write(_readings(3)) == WriteResult(rows=3)
        assert writer.write(_readings(3)) == WriteResult()  # acelasi lot, retrimis
        assert writer.write(_readings(4)) == WriteResult(rows=1)  # lot partial nou
        assert writer.write([]) == WriteResult()
    finally:
        writer.close()
    assert _count(conninfo) == 4


def test_unique_key_migration_removes_existing_duplicates(conninfo: str) -> None:
    # Baza asa cum a lasat-o FP-201: doar migrarea 1, fara cheie unica, cu un duplicat.
    with psycopg.connect(conninfo) as conn:
        conn.execute(MIGRATIONS[0][1])
        for _ in range(2):
            conn.execute(
                "INSERT INTO telemetry VALUES (%s, 'motor', 't', 1.0, 'C', %s)", (WHEN, WHEN)
            )
    assert _count(conninfo) == 2

    with psycopg.connect(conninfo) as conn:
        assert migrate(conn) == [1, 2, 3]
        assert migrate(conn) == []  # a doua oara nu mai e nimic de aplicat
    assert _count(conninfo) == 1


def test_quarantine_is_written_with_telemetry_and_is_idempotent(conninfo: str) -> None:
    raw = b"\xff nu e json"
    rejected = [Rejected(Received("factory/motor/t", raw, 1, 1, WHEN), "payload_invalid", "x")]
    writer = PostgresWriter(conninfo)
    try:
        assert writer.write(_readings(2), rejected) == WriteResult(rows=2, quarantined=1)
        assert writer.write(_readings(2), rejected) == WriteResult()  # lot retrimis
    finally:
        writer.close()
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute("SELECT topic, payload, reason FROM quarantine").fetchall()
    assert rows == [("factory/motor/t", raw, "payload_invalid")]
