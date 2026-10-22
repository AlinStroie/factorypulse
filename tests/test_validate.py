"""Teste pentru validarea de baza: fiecare regula respinge ce trebuie si lasa sa treaca restul."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from factorypulse.bridge.mapping import payload_for
from factorypulse.ingestor.batch import Reading, Received
from factorypulse.ingestor.validate import (
    LIMITS,
    OUT_OF_LIMITS,
    PAYLOAD_INVALID,
    UNKNOWN_UNIT,
    VALUE_NOT_FINITE,
    Rejected,
    validate,
)
from factorypulse.simulator.model import MACHINES

WHEN = datetime(2026, 10, 22, 8, 0, 0, tzinfo=UTC)


def _received(payload: str) -> Received:
    return Received("factory/motor/temperatura", payload.encode(), 1, 1, WHEN)


def _reading(value: float, unit: str = "C", sensor: str = "temperatura") -> Received:
    return _received(payload_for("motor", sensor, value, unit, WHEN))


def _reason(message: Received) -> str | None:
    result = validate(message)
    return result.reason if isinstance(result, Rejected) else None


def test_normal_reading_is_valid() -> None:
    assert isinstance(validate(_reading(65.0)), Reading)


def test_real_fault_is_not_quarantined() -> None:
    # Supraincalzirea injectata de simulator (65 + 12 C) e o anomalie, nu o eroare de date.
    assert isinstance(validate(_reading(77.0)), Reading)


@pytest.mark.parametrize("value", [-50.0, 250.0])
def test_limits_are_inclusive(value: float) -> None:
    assert isinstance(validate(_reading(value)), Reading)


@pytest.mark.parametrize("value", [-273.0, 9999.0, 250.01])
def test_value_outside_physical_limits(value: float) -> None:
    result = validate(_reading(value))
    assert isinstance(result, Rejected)
    assert result.reason == OUT_OF_LIMITS
    assert "limite -50..250" in result.detail


def test_negative_pressure_is_rejected() -> None:
    assert _reason(_reading(-0.5, "bar", "presiune")) == OUT_OF_LIMITS


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_value(token: str) -> None:
    # json.dumps scrie NaN/Infinity ca token-uri nestandard, iar json.loads le accepta.
    payload = json.dumps(
        {"machine": "motor", "sensor": "t", "ts": WHEN.isoformat(), "value": 0, "unit": "C"}
    ).replace('"value": 0', f'"value": {token}')
    assert _reason(_received(payload)) == VALUE_NOT_FINITE


def test_unknown_unit() -> None:
    assert _reason(_reading(65.0, "F")) == UNKNOWN_UNIT


def test_unreadable_payload() -> None:
    assert _reason(_received("nu e json")) == PAYLOAD_INVALID


def test_late_and_out_of_order_data_is_accepted() -> None:
    # ADR-021: ordinea se stabileste dupa ts, nu dupa sosire.
    old = _received(payload_for("motor", "temperatura", 65.0, "C", WHEN - timedelta(hours=6)))
    assert isinstance(validate(old), Reading)


def test_every_simulated_unit_has_limits() -> None:
    units = {sensor.unit for machine in MACHINES for sensor in machine.sensors}
    assert units <= set(LIMITS)
