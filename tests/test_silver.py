"""Teste pentru jobul silver: deduplicare, tipuri, partitionare dupa eveniment, idempotenta."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from factorypulse.bridge.mapping import payload_for
from factorypulse.ingestor.batch import Received
from factorypulse.ingestor.bronze import BronzeWriter
from factorypulse.silver.__main__ import main
from factorypulse.silver.build import SCHEMA, bronze_days_for, build

DAY = date(2026, 10, 22)
T0 = datetime(2026, 10, 22, 10, 0, 0, tzinfo=UTC)


def _msg(
    ts: datetime, arrived: datetime, value: float = 65.0, sensor: str = "temperatura"
) -> Received:
    payload = payload_for("motor", sensor, value, "C", ts).encode()
    return Received(f"factory/motor/{sensor}", payload, 1, 1, arrived)


def _silver(root: Path, day: date = DAY) -> pd.DataFrame:
    return pd.read_parquet(root / "telemetry" / f"date={day:%Y-%m-%d}")


def test_bronze_window_follows_validation_window() -> None:
    days = bronze_days_for(DAY)
    assert days[0] == DAY - timedelta(days=1)
    assert days[-1] == DAY + timedelta(days=7)
    assert len(days) == 9


def test_duplicates_keep_first_arrival(tmp_path: Path) -> None:
    bronze = BronzeWriter(tmp_path / "bronze")
    bronze.write([_msg(T0, T0 + timedelta(seconds=1))])
    # Acelasi mesaj, retrimis de broker dupa o repornire, in alt fisier bronze.
    bronze.write([_msg(T0, T0 + timedelta(seconds=30))])

    stats = build(tmp_path / "bronze", tmp_path / "silver", [DAY])

    assert (stats.valid, stats.duplicates, stats.rows_per_day[DAY]) == (2, 1, 1)
    df = _silver(tmp_path / "silver")
    assert df["ingestion_ts"].tolist() == [pd.Timestamp(T0 + timedelta(seconds=1))]


def test_silver_has_exact_types(tmp_path: Path) -> None:
    """AC FP-205: tipuri corecte."""
    BronzeWriter(tmp_path / "bronze").write([_msg(T0, T0)])
    build(tmp_path / "bronze", tmp_path / "silver", [DAY])
    files = list((tmp_path / "silver" / "telemetry").rglob("*.parquet"))
    assert len(files) == 1
    assert pq.read_schema(files[0]).remove_metadata() == SCHEMA


def test_invalid_rows_are_counted_not_written(tmp_path: Path) -> None:
    raw = Received("factory/motor/temperatura", b"nu e json", 1, 1, T0)
    BronzeWriter(tmp_path / "bronze").write([raw, _msg(T0, T0, value=-273.0), _msg(T0, T0)])

    stats = build(tmp_path / "bronze", tmp_path / "silver", [DAY])

    assert dict(stats.rejected) == {"payload_invalid": 1, "in_afara_limitelor": 1}
    assert len(_silver(tmp_path / "silver")) == 1


def test_late_arrival_lands_in_event_day(tmp_path: Path) -> None:
    # Eveniment pe 22, sosit pe 24: bronze il are in dt=2026-10-24, silver in date=2026-10-22.
    late = _msg(T0, T0 + timedelta(days=2))
    BronzeWriter(tmp_path / "bronze").write([late])
    assert (tmp_path / "bronze" / "telemetry" / "dt=2026-10-24").is_dir()

    build(tmp_path / "bronze", tmp_path / "silver", [DAY])

    assert _silver(tmp_path / "silver")["ts"].tolist() == [pd.Timestamp(T0)]


def test_only_requested_days_are_written(tmp_path: Path) -> None:
    bronze = BronzeWriter(tmp_path / "bronze")
    bronze.write([_msg(T0, T0), _msg(T0 + timedelta(days=1), T0 + timedelta(days=1))])

    stats = build(tmp_path / "bronze", tmp_path / "silver", [DAY])

    assert stats.rows_per_day == {DAY: 1}
    assert [p.name for p in (tmp_path / "silver" / "telemetry").iterdir()] == ["date=2026-10-22"]


def test_rebuild_is_idempotent_and_reflects_new_bronze(tmp_path: Path) -> None:
    bronze = BronzeWriter(tmp_path / "bronze")
    bronze.write([_msg(T0, T0)])
    build(tmp_path / "bronze", tmp_path / "silver", [DAY])
    first = _silver(tmp_path / "silver")
    build(tmp_path / "bronze", tmp_path / "silver", [DAY])
    pd.testing.assert_frame_equal(first, _silver(tmp_path / "silver"))

    bronze.write([_msg(T0 + timedelta(minutes=1), T0 + timedelta(minutes=1))])
    build(tmp_path / "bronze", tmp_path / "silver", [DAY])
    assert len(_silver(tmp_path / "silver")) == 2
    leftovers = [p for p in (tmp_path / "silver").rglob("*") if p.name.startswith(".")]
    assert leftovers == []


def test_day_without_valid_data_is_removed(tmp_path: Path) -> None:
    BronzeWriter(tmp_path / "bronze").write([_msg(T0, T0)])
    build(tmp_path / "bronze", tmp_path / "silver", [DAY])
    empty_bronze = tmp_path / "bronze-gol"

    stats = build(empty_bronze, tmp_path / "silver", [DAY])

    assert stats.rows_per_day == {DAY: 0}
    assert not (tmp_path / "silver" / "telemetry" / "date=2026-10-22").exists()


def test_cli_builds_requested_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    BronzeWriter(tmp_path / "bronze").write([_msg(T0, T0)])
    monkeypatch.setenv("BRONZE_DIR", str(tmp_path / "bronze"))
    monkeypatch.setenv("SILVER_DIR", str(tmp_path / "silver"))

    assert main(["--from", "2026-10-22", "--to", "2026-10-22"]) == 0

    assert "silver 2026-10-22: 1 randuri" in capsys.readouterr().out


def test_cli_rejects_inverted_range() -> None:
    with pytest.raises(SystemExit):
        main(["--from", "2026-10-23", "--to", "2026-10-22"])
