"""Construieste silver din bronze: aceeasi validare ca ingestorul, deduplicare, tipuri fixe.

    bronze/telemetry/dt=<ziua sosirii>/      ->      silver/telemetry/date=<ziua evenimentului>/

Fiecare zi ceruta se reconstruieste complet si se inlocuieste atomic, deci jobul e
idempotent: rulat de doua ori, da acelasi rezultat. Dupa o corectura intr-o regula de
validare, rularea din nou repara silver retroactiv.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from factorypulse.contract import MAX_AGE, MAX_AHEAD
from factorypulse.ingestor import bronze
from factorypulse.ingestor.batch import Reading, Received
from factorypulse.ingestor.validate import Rejected, validate

log = logging.getLogger(__name__)

SCHEMA = pa.schema(
    [
        ("ts", pa.timestamp("us", tz="UTC")),
        ("machine", pa.string()),
        ("sensor", pa.string()),
        ("value", pa.float64()),
        ("unit", pa.string()),
        ("ingestion_ts", pa.timestamp("us", tz="UTC")),
    ]
)
KEY = ["machine", "sensor", "ts"]


@dataclass
class BuildStats:
    bronze_rows: int = 0
    valid: int = 0
    duplicates: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    rows_per_day: dict[date, int] = field(default_factory=dict)


def bronze_days_for(day: date) -> list[date]:
    """Zilele de sosire care pot contine evenimente din `day`.

    Un mesaj valid soseste cel mult cu MAX_AHEAD inainte de `ts` si cel mult cu MAX_AGE
    dupa (FP-208); altfel e in carantina. Fereastra de validare margineste deci cat
    bronze trebuie citit pentru o zi.
    """
    first = day - timedelta(days=MAX_AHEAD.days + 1)
    last = day + timedelta(days=MAX_AGE.days)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def read_bronze(bronze_root: Path, days: Iterable[date]) -> pa.Table:
    tables = []
    for day in sorted(set(days)):
        partition = bronze_root / "telemetry" / f"dt={day:%Y-%m-%d}"
        if partition.is_dir():
            # Citirea unui director ignora fisierele temporare (incep cu punct).
            tables.append(pq.read_table(partition, schema=bronze.SCHEMA))
    if not tables:
        return bronze.SCHEMA.empty_table()
    return pa.concat_tables(tables)


def _validated(raw: pa.Table, stats: BuildStats) -> pd.DataFrame:
    readings: list[Reading] = []
    columns = raw.to_pydict()
    for topic, payload, ingestion_ts in zip(
        columns["topic"], columns["payload"], columns["ingestion_ts"], strict=True
    ):
        # mid si qos tin de MQTT; aici nu se folosesc.
        result = validate(Received(topic, payload, 0, 0, ingestion_ts))
        if isinstance(result, Rejected):
            stats.rejected[result.reason] += 1
        else:
            readings.append(result)
    stats.valid = len(readings)
    return pd.DataFrame(
        {
            "ts": [r.ts for r in readings],
            "machine": [r.machine for r in readings],
            "sensor": [r.sensor for r in readings],
            "value": [r.value for r in readings],
            "unit": [r.unit for r in readings],
            "ingestion_ts": [r.ingestion_ts for r in readings],
        }
    )


def _write_day_atomic(table: pa.Table, partition: Path) -> None:
    """Ziua noua se scrie intr-un director temporar, apoi inlocuieste ziua veche.

    Un cititor vede fie ziua veche, fie pe cea noua, niciodata una pe jumatate.
    """
    partition.parent.mkdir(parents=True, exist_ok=True)
    tmp = partition.with_name(f".{partition.name}.tmp")
    old = partition.with_name(f".{partition.name}.old")
    for leftover in (tmp, old):
        shutil.rmtree(leftover, ignore_errors=True)
    tmp.mkdir()
    with open(tmp / "part-0.parquet", "wb") as f:
        pq.write_table(table, f, compression="zstd")
        f.flush()
        os.fsync(f.fileno())
    if partition.exists():
        os.replace(partition, old)
    os.replace(tmp, partition)
    shutil.rmtree(old, ignore_errors=True)


def build(bronze_root: Path, silver_root: Path, days: Iterable[date]) -> BuildStats:
    days = sorted(set(days))
    stats = BuildStats()
    raw = read_bronze(bronze_root, (d for day in days for d in bronze_days_for(day)))
    stats.bronze_rows = raw.num_rows

    df = _validated(raw, stats)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df["ingestion_ts"] = pd.to_datetime(df["ingestion_ts"], utc=True)
        # Duplicatele (mesaje retrimise de broker): se pastreaza prima sosire.
        df = df.sort_values([*KEY, "ingestion_ts"], kind="stable")
        before = len(df)
        df = df.drop_duplicates(subset=KEY, keep="first")
        stats.duplicates = before - len(df)
    event_day = df["ts"].dt.date if not df.empty else pd.Series(dtype=object)

    table_dir = silver_root / "telemetry"
    for day in days:
        rows = df[event_day == day] if not df.empty else df
        partition = table_dir / f"date={day:%Y-%m-%d}"
        stats.rows_per_day[day] = len(rows)
        if rows.empty:
            # Ziua nu mai are date valide: silver trebuie sa reflecte asta.
            shutil.rmtree(partition, ignore_errors=True)
            continue
        table = pa.Table.from_pandas(
            rows[SCHEMA.names].sort_values(["ts", "machine", "sensor"]),
            schema=SCHEMA,
            preserve_index=False,
        )
        _write_day_atomic(table, partition)
    log.info(
        "silver: %d randuri bronze, %d valide, %d duplicate, respinse %s, pe zile %s",
        stats.bronze_rows,
        stats.valid,
        stats.duplicates,
        dict(stats.rejected),
        {d.isoformat(): n for d, n in stats.rows_per_day.items()},
    )
    return stats
