"""Scrierea in TimescaleDB: schema si insert pe loturi."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import psycopg

from factorypulse.ingestor.batch import Reading

log = logging.getLogger(__name__)

# IF NOT EXISTS: se poate rula la fiecare pornire, si pe un volum care are deja date.
# Cheia unica (masina, senzor, ts) vine in FP-202.
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS telemetry (
    ts           timestamptz      NOT NULL,
    machine      text             NOT NULL,
    sensor       text             NOT NULL,
    value        double precision NOT NULL,
    unit         text             NOT NULL,
    ingestion_ts timestamptz      NOT NULL
);
SELECT create_hypertable('telemetry', by_range('ts'), if_not_exists => TRUE);
"""

# executemany in loc de COPY: COPY e mai rapid, dar nu accepta ON CONFLICT, de care
# FP-202 are nevoie. psycopg 3 trimite executemany in pipeline, deci tot un singur drum.
INSERT_SQL = """
INSERT INTO telemetry (ts, machine, sensor, value, unit, ingestion_ts)
VALUES (%s, %s, %s, %s, %s, %s)
"""


class PostgresWriter:
    """Pastreaza o conexiune deschisa si o reface dupa o eroare."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        self._conn: psycopg.Connection[tuple[object, ...]] | None = None

    def _connection(self) -> psycopg.Connection[tuple[object, ...]]:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._conninfo)
            with self._conn.transaction():
                self._conn.execute(SCHEMA_SQL)
            log.info("conectat la TimescaleDB, schema verificata")
        return self._conn

    def write(self, readings: Sequence[Reading]) -> None:
        """Un lot = o tranzactie. La eroare nu se scrie nimic din lot."""
        if not readings:
            return
        try:
            conn = self._connection()
            with conn.transaction(), conn.cursor() as cur:
                cur.executemany(
                    INSERT_SQL,
                    [
                        (r.ts, r.machine, r.sensor, r.value, r.unit, r.ingestion_ts)
                        for r in readings
                    ],
                )
        except psycopg.OperationalError:
            self.close()
            raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
