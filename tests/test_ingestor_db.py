"""Test pe un TimescaleDB real. Ruleaza doar daca FP_TEST_POSTGRES este setat.

Exemplu: FP_TEST_POSTGRES="host=127.0.0.1 user=factory password=... dbname=factorypulse"
In CI, containerele vin in FP-206.
"""

import os
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from factorypulse.ingestor.batch import Reading
from factorypulse.ingestor.db import PostgresWriter

CONNINFO = os.getenv("FP_TEST_POSTGRES")
pytestmark = pytest.mark.skipif(not CONNINFO, reason="FP_TEST_POSTGRES nu e setat")

WHEN = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)  # in trecut, ca sa nu se amestece cu datele live


def test_writer_creates_schema_and_inserts_batch() -> None:
    assert CONNINFO is not None
    machine = f"test-{os.getpid()}"
    readings = [
        Reading(machine, "t", WHEN + timedelta(seconds=i), float(i), "C", WHEN) for i in range(3)
    ]
    writer = PostgresWriter(CONNINFO)
    try:
        writer.write(readings)
        writer.write([])
    finally:
        writer.close()

    with psycopg.connect(CONNINFO) as conn:
        count = conn.execute("SELECT count(*) FROM telemetry WHERE machine = %s", (machine,))
        assert count.fetchone() == (3,)
        conn.execute("DELETE FROM telemetry WHERE machine = %s", (machine,))
