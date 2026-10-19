"""Teste pentru defectele injectate si etichetele de adevar."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from factorypulse.simulator.faults import FAULT_KINDS, Fault, FaultSchedule, random_schedule


def test_offset_is_zero_outside_interval_and_magnitude_inside() -> None:
    fault = Fault("motor", "temperatura", "supraincalzire", 100.0, 200.0, 12.0)
    assert fault.offset("motor", "temperatura", 50.0) == 0.0
    assert fault.offset("motor", "temperatura", 150.0) == 12.0
    assert fault.offset("motor", "temperatura", 250.0) == 0.0


def test_offset_ignores_other_machines_and_sensors() -> None:
    fault = Fault("motor", "temperatura", "supraincalzire", 0.0, 100.0, 12.0)
    assert fault.offset("pompa", "temperatura", 50.0) == 0.0
    assert fault.offset("motor", "vibratie", 50.0) == 0.0


def test_random_schedule_is_reproducible() -> None:
    assert (
        random_schedule(seed=5, duration_s=3600).faults
        == random_schedule(seed=5, duration_s=3600).faults
    )


def test_every_fault_has_valid_label() -> None:
    schedule = random_schedule(seed=11, duration_s=3600, count=5)
    for fault in schedule.faults:
        assert fault.kind in FAULT_KINDS
        assert fault.start_s < fault.end_s
        assert fault.start_s >= 0.0


def test_ground_truth_round_trip(tmp_path: Path) -> None:
    schedule = random_schedule(seed=2, duration_s=1800)
    schedule.started_at = datetime(2026, 10, 19, 8, 0, 0, tzinfo=UTC)
    path = tmp_path / "ground_truth.json"
    schedule.save(path)
    loaded = FaultSchedule.load(path)
    assert loaded.faults == schedule.faults
    assert loaded.started_at == schedule.started_at


def test_ground_truth_has_absolute_timestamps(tmp_path: Path) -> None:
    started = datetime(2026, 10, 19, 8, 0, 0, tzinfo=UTC)
    fault = Fault("motor", "temperatura", "supraincalzire", 90.0, 150.0, 12.0)
    path = tmp_path / "ground_truth.json"
    FaultSchedule([fault], started_at=started).save(path)
    record = json.loads(path.read_text(encoding="utf-8"))["faults"][0]
    assert datetime.fromisoformat(record["start_ts"]) == started + timedelta(seconds=90)
    assert datetime.fromisoformat(record["end_ts"]) == started + timedelta(seconds=150)


def test_save_without_start_time_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        FaultSchedule([]).save(tmp_path / "ground_truth.json")


def test_random_schedule_has_no_overlap_on_same_sensor() -> None:
    for seed in range(50):
        faults = random_schedule(seed=seed, duration_s=3600, count=6).faults
        for i, first in enumerate(faults):
            for second in faults[i + 1 :]:
                assert not first.overlaps(second), (seed, first, second)


def test_random_schedule_fails_when_faults_cannot_fit() -> None:
    with pytest.raises(ValueError):
        random_schedule(seed=1, duration_s=200, count=20)
