"""Teste pentru stratul bronze: fisiere Parquet partitionate pe zi si compactarea orara."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from factorypulse.ingestor.batch import Received
from factorypulse.ingestor.bronze import SCHEMA, BronzeWriter

T0 = datetime(2026, 10, 21, 10, 15, 0, tzinfo=UTC)


def _msg(mid: int, at: datetime, payload: bytes = b'{"value": 1}') -> Received:
    return Received(f"factory/motor/s{mid}", payload, mid, 1, at)


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.parquet"))


def test_batch_is_readable_with_pandas(tmp_path: Path) -> None:
    """AC FP-203: fisierele se citesc cu pandas."""
    BronzeWriter(tmp_path).write([_msg(1, T0), _msg(2, T0 + timedelta(seconds=1))])
    df = pd.read_parquet(tmp_path / "telemetry")
    assert list(df.columns) == ["ingestion_ts", "topic", "payload", "dt"]
    assert df["topic"].tolist() == ["factory/motor/s1", "factory/motor/s2"]
    assert df["payload"].tolist() == [b'{"value": 1}', b'{"value": 1}']
    assert df["ingestion_ts"].iloc[0] == pd.Timestamp(T0)
    assert set(df["dt"].astype(str)) == {"2026-10-21"}


def test_invalid_payload_is_kept_byte_for_byte(tmp_path: Path) -> None:
    raw = b"\xff\xfe nu e json"
    (path,) = BronzeWriter(tmp_path).write([_msg(1, T0, raw)])
    assert pq.read_table(path).column("payload").to_pylist() == [raw]


def test_batch_across_midnight_goes_to_two_partitions(tmp_path: Path) -> None:
    late = datetime(2026, 10, 21, 23, 59, 59, 900000, tzinfo=UTC)
    paths = BronzeWriter(tmp_path).write([_msg(1, late), _msg(2, late + timedelta(seconds=1))])
    assert [p.parent.name for p in paths] == ["dt=2026-10-21", "dt=2026-10-22"]
    assert paths[0].name.startswith("part-23-") and paths[1].name.startswith("part-00-")


def test_no_temporary_files_are_left(tmp_path: Path) -> None:
    BronzeWriter(tmp_path).write([_msg(1, T0)])
    assert not [p for p in tmp_path.rglob("*") if p.name.startswith(".")]


def test_compaction_merges_finished_hours_only(tmp_path: Path) -> None:
    bronze = BronzeWriter(tmp_path)
    for i in range(5):
        bronze.write([_msg(i, T0 + timedelta(minutes=i))])  # ora 10
    bronze.write([_msg(9, T0 + timedelta(hours=1))])  # ora 11, inca in curs

    removed = bronze.compact(before=datetime(2026, 10, 21, 11, tzinfo=UTC))

    assert removed == 5
    files = _files(tmp_path)
    assert files[0] == "telemetry/dt=2026-10-21/hour-10.parquet"
    assert len(files) == 2 and files[1].startswith("telemetry/dt=2026-10-21/part-11-")
    hour = pq.read_table(tmp_path / files[0])
    assert hour.schema == SCHEMA
    assert hour.column("topic").to_pylist() == [f"factory/motor/s{i}" for i in range(5)]
    assert len(pd.read_parquet(tmp_path / "telemetry")) == 6


def test_late_files_are_merged_into_existing_hour(tmp_path: Path) -> None:
    bronze = BronzeWriter(tmp_path)
    end_of_hour = datetime(2026, 10, 21, 11, tzinfo=UTC)
    bronze.write([_msg(1, T0)])
    bronze.compact(before=end_of_hour)
    bronze.write([_msg(2, T0 + timedelta(minutes=1))])  # sosit dupa compactare

    assert bronze.compact(before=end_of_hour) == 1
    assert _files(tmp_path) == ["telemetry/dt=2026-10-21/hour-10.parquet"]
    assert len(pd.read_parquet(tmp_path / "telemetry")) == 2


def test_compaction_without_files_does_nothing(tmp_path: Path) -> None:
    assert BronzeWriter(tmp_path).compact(before=T0) == 0
