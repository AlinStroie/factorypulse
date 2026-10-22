"""Scrierea in TimescaleDB: migrarile schemei, telemetria si carantina, pe loturi."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import psycopg

from factorypulse.ingestor.batch import Reading
from factorypulse.ingestor.validate import Rejected

log = logging.getLogger(__name__)

# Migrarile se aplica in ordine, fiecare o singura data, si nu se modifica dupa ce au ajuns
# in main: o schimbare noua de schema inseamna o migrare noua la finalul listei.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        # IF NOT EXISTS: bazele create inainte de tabelul schema_migrations au deja tabelul.
        """
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
        """,
    ),
    (
        2,
        # FP-202: cheia unica face reincarcarea sigura (ADR-020). Duplicatele existente se
        # sterg intai, altfel indexul nu se poate crea. Randurile cu aceeasi cheie au acelasi
        # ts, deci sunt in acelasi chunk; tableoid + ctid identifica randul in chunk.
        # Pe o hypertable, un index unic trebuie sa contina coloana de partitionare (ts).
        """
        DELETE FROM telemetry a
        USING telemetry b
        WHERE a.machine = b.machine AND a.sensor = b.sensor AND a.ts = b.ts
          AND a.tableoid = b.tableoid AND a.ctid > b.ctid;
        CREATE UNIQUE INDEX IF NOT EXISTS telemetry_machine_sensor_ts_key
            ON telemetry (machine, sensor, ts);
        """,
    ),
    (
        3,
        # FP-204: mesajele respinse de validare, intregi, ca sa poata fi analizate si
        # reprocesate. Indexul unic face carantina idempotenta, ca telemetria: un mesaj
        # retrimis de broker nu apare de doua ori. md5 e doar amprenta, nu securitate.
        """
        CREATE TABLE IF NOT EXISTS quarantine (
            id           bigserial   PRIMARY KEY,
            ingestion_ts timestamptz NOT NULL,
            topic        text        NOT NULL,
            payload      bytea       NOT NULL,
            reason       text        NOT NULL,
            detail       text        NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS quarantine_topic_payload_key
            ON quarantine (topic, md5(payload));
        CREATE INDEX IF NOT EXISTS quarantine_ingestion_ts_idx ON quarantine (ingestion_ts);
        """,
    ),
]

# Daca pornesc doua ingestoare deodata, doar unul aplica migrarile; celalalt asteapta.
_MIGRATION_LOCK = 20260202

INSERT_SQL = """
INSERT INTO telemetry (ts, machine, sensor, value, unit, ingestion_ts)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (machine, sensor, ts) DO NOTHING
"""

QUARANTINE_SQL = """
INSERT INTO quarantine (ingestion_ts, topic, payload, reason, detail)
VALUES (%s, %s, %s, %s, %s)
ON CONFLICT (topic, md5(payload)) DO NOTHING
"""


@dataclass(frozen=True)
class WriteResult:
    """Randurile noi scrise; cele care existau deja (mesaje retrimise) nu se numara."""

    rows: int = 0
    quarantined: int = 0


def pending_migrations(applied: set[int]) -> list[tuple[int, str]]:
    return [(version, sql) for version, sql in MIGRATIONS if version not in applied]


def migrate(conn: psycopg.Connection[tuple[object, ...]]) -> list[int]:
    """Aplica migrarile lipsa, intr-o singura tranzactie. Intoarce versiunile aplicate."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            " version integer PRIMARY KEY,"
            " applied_at timestamptz NOT NULL DEFAULT now())"
        )
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {version for (version,) in rows if isinstance(version, int)}
        done: list[int] = []
        for version, sql in pending_migrations(applied):
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
            done.append(version)
    return done


class PostgresWriter:
    """Pastreaza o conexiune deschisa si o reface dupa o eroare."""

    def __init__(self, conninfo: str) -> None:
        self._conninfo = conninfo
        self._conn: psycopg.Connection[tuple[object, ...]] | None = None

    def _connection(self) -> psycopg.Connection[tuple[object, ...]]:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self._conninfo)
            applied = migrate(self._conn)
            log.info("conectat la TimescaleDB, migrari aplicate acum: %s", applied or "niciuna")
        return self._conn

    def write(self, readings: Sequence[Reading], rejected: Sequence[Rejected] = ()) -> WriteResult:
        """Un lot = o tranzactie, pentru ambele tabele: ori se scrie tot, ori nimic.

        Randurile care exista deja sunt sarite, deci un lot retrimis de broker dupa o
        cadere nu creeaza duplicate, nici in telemetrie, nici in carantina.
        """
        if not readings and not rejected:
            return WriteResult()
        try:
            conn = self._connection()
            with conn.transaction(), conn.cursor() as cur:
                rows = quarantined = 0
                # Dupa executemany, rowcount e suma randurilor inserate efectiv.
                if readings:
                    cur.executemany(
                        INSERT_SQL,
                        [
                            (r.ts, r.machine, r.sensor, r.value, r.unit, r.ingestion_ts)
                            for r in readings
                        ],
                    )
                    rows = cur.rowcount
                if rejected:
                    cur.executemany(
                        QUARANTINE_SQL,
                        [
                            (
                                r.message.ingestion_ts,
                                r.message.topic,
                                r.message.payload,
                                r.reason,
                                r.detail,
                            )
                            for r in rejected
                        ],
                    )
                    quarantined = cur.rowcount
                return WriteResult(rows, quarantined)
        except psycopg.OperationalError:
            self.close()
            raise

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
