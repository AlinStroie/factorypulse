"""Teste pe un TimescaleDB real. Ruleaza doar daca FP_TEST_POSTGRES este setat.

Exemplu: FP_TEST_POSTGRES="host=127.0.0.1 user=factory password=... dbname=factorypulse"
Fiecare test lucreaza intr-o schema proprie, stearsa la final, deci nu atinge datele live.
In CI, containerele vin in FP-206.
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from factorypulse.ingestor.batch import Reading
from factorypulse.ingestor.db import MIGRATIONS, PostgresWriter, migrate

CONNINFO = os.getenv("FP_TEST_POSTGRES")
pytestmark = pytest.mark.skipif(not CONNINFO, reason="FP_TEST_POSTGRES nu e setat")

WHEN = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)


def _readings(n: int) -> list[Reading]:
    return [
        Reading("motor", "t", WHEN + timedelta(seconds=i), float(i), "C", WHEN) for i in range(n)
    ]


@pytest.fixture
def conninfo() -> Iterator[str]:
    """Conninfo cu search_path pe o schema temporara."""
    assert CONNINFO is not None
    schema = f"fp_test_{os.getpid()}"
    with psycopg.connect(CONNINFO, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.execute(f"CREATE SCHEMA {schema}")
    yield f"{CONNINFO} options='-c search_path={schema},public'"
    with psycopg.connect(CONNINFO, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")


def _count(conninfo: str) -> object:
    with psycopg.connect(conninfo) as conn:
        row = conn.execute("SELECT count(*) FROM telemetry").fetchone()
    assert row is not None
    return row[0]


def test_reprocessing_does_not_create_duplicates(conninfo: str) -> None:
    writer = PostgresWriter(conninfo)
    try:
        assert writer.write(_readings(3)) == 3
        assert writer.write(_readings(3)) == 0  # acelasi lot, retrimis
        assert writer.write(_readings(4)) == 1  # lot partial nou
        assert writer.write([]) == 0
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
        assert migrate(conn) == [1, 2]
        assert migrate(conn) == []  # a doua oara nu mai e nimic de aplicat
    assert _count(conninfo) == 1
