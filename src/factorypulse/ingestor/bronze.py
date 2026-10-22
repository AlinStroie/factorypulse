"""Stratul bronze: mesajele brute in Parquet, exact cum au venit (ADR-020).

Structura pe disc (partitionare Hive, citita direct de pandas, pyarrow si Spark):

    <root>/telemetry/dt=2026-10-21/part-14-<timp>-<id>.parquet   un fisier per lot
    <root>/telemetry/dt=2026-10-21/hour-13.parquet               o ora compactata

Partitia e ziua sosirii (`ingestion_ts`), nu ziua evenimentului: un mesaj stricat poate
sa nu aiba `ts`, dar are mereu momentul sosirii. Partitionarea dupa eveniment e in silver.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from factorypulse.ingestor.batch import Received

log = logging.getLogger(__name__)

SCHEMA = pa.schema(
    [
        ("ingestion_ts", pa.timestamp("us", tz="UTC")),
        ("topic", pa.string()),
        ("payload", pa.binary()),
    ]
)


def _hour_of(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


def _write_atomic(table: pa.Table, path: Path) -> None:
    """Scrie intr-un fisier temporar, fsync, apoi redenumeste.

    Un cititor nu vede niciodata un fisier scris pe jumatate. Numele temporar incepe cu
    punct, iar pyarrow ignora astfel de fisiere cand citeste un director.
    """
    tmp = path.with_name(f".{path.name}.tmp")
    with open(tmp, "wb") as f:
        pq.write_table(table, f, compression="zstd")
        f.flush()
        # Fara fsync, datele pot ramane doar in memoria sistemului de operare; dupa ack,
        # o cadere de curent le-ar pierde.
        os.fsync(f.fileno())
    os.replace(tmp, path)


class BronzeWriter:
    def __init__(self, root: Path) -> None:
        self._table_dir = root / "telemetry"

    def _partition(self, hour: datetime) -> Path:
        return self._table_dir / f"dt={hour:%Y-%m-%d}"

    def write(self, items: Sequence[Received]) -> list[Path]:
        """Un fisier per (zi, ora) din lot; de obicei unul singur. Intoarce fisierele scrise."""
        by_hour: dict[datetime, list[Received]] = defaultdict(list)
        for item in items:
            by_hour[_hour_of(item.ingestion_ts)].append(item)
        paths: list[Path] = []
        for hour, group in sorted(by_hour.items()):
            table = pa.table(
                {
                    "ingestion_ts": [m.ingestion_ts for m in group],
                    "topic": [m.topic for m in group],
                    "payload": [m.payload for m in group],
                },
                schema=SCHEMA,
            )
            partition = self._partition(hour)
            partition.mkdir(parents=True, exist_ok=True)
            first = group[0].ingestion_ts
            path = partition / f"part-{hour:%H}-{first:%H%M%S%f}-{uuid.uuid4().hex[:8]}.parquet"
            _write_atomic(table, path)
            paths.append(path)
        return paths

    def compact(self, before: datetime) -> int:
        """Uneste fisierele mici ale fiecarei ore terminate inainte de `before` intr-unul singur.

        Daca ora are deja un fisier compactat (au venit fisiere intarziate), il include.
        Intoarce numarul de fisiere mici sterse.
        """
        groups: dict[Path, list[Path]] = defaultdict(list)
        for part in self._table_dir.glob("dt=*/part-*.parquet"):
            day = part.parent.name.removeprefix("dt=")
            hour = datetime.fromisoformat(f"{day}T{part.name[5:7]}:00:00+00:00")
            if hour + timedelta(hours=1) <= before:
                groups[part.parent / f"hour-{hour:%H}.parquet"].append(part)

        removed = 0
        for target, parts in sorted(groups.items()):
            sources = ([target] if target.exists() else []) + sorted(parts)
            table = pa.concat_tables(pq.read_table(p, schema=SCHEMA) for p in sources)
            # Intai fisierul mare, apoi stergerea celor mici. Intre cei doi pasi, un cititor
            # poate vedea randuri de doua ori; silver deduplica (FP-205).
            _write_atomic(table.sort_by("ingestion_ts"), target)
            for part in parts:
                part.unlink()
            removed += len(parts)
            log.info("compactat %s: %d fisiere, %d randuri", target, len(parts), table.num_rows)
        return removed
