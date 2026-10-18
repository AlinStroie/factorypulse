"""Teste pentru defectele injectate si etichetele de adevar."""

from pathlib import Path

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
    path = tmp_path / "ground_truth.json"
    schedule.save(path)
    assert FaultSchedule.load(path).faults == schedule.faults
