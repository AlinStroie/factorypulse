"""Teste pentru validare: contractul v1, fereastra de timp si regulile de valoare."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from factorypulse.bridge.mapping import payload_for
from factorypulse.ingestor.batch import Reading, Received
from factorypulse.ingestor.validate import (
    CONTRACT_INVALID,
    LIMITS,
    OUT_OF_LIMITS,
    PAYLOAD_INVALID,
    TS_AHEAD,
    TS_TOO_OLD,
    UNKNOWN_UNIT,
    UNSUPPORTED_VERSION,
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


def _payload(**changes: object) -> str:
    """Un payload v1 valid, cu campurile din `changes` inlocuite (None = camp sters)."""
    data: dict[str, object] = json.loads(payload_for("motor", "temperatura", 65.0, "C", WHEN))
    for key, value in changes.items():
        if value is None:
            del data[key]
        else:
            data[key] = value
    return json.dumps(data)


def test_valid_reading_keeps_all_fields() -> None:
    result = validate(_reading(65.0))
    assert result == Reading("motor", "temperatura", WHEN, 65.0, "C", WHEN)


# --- contract v1 (FP-208) ------------------------------------------------------------------


@pytest.mark.parametrize("version", [2, 0, "1", True, None])
def test_unsupported_schema_version(version: object) -> None:
    # None = camp lipsa
    assert _reason(_received(_payload(schema_version=version))) == UNSUPPORTED_VERSION


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"value": None}, "value"),
        ({"machine": None}, "machine"),
        ({"value": "65.1"}, "value"),
        ({"value": True}, "value"),
        ({"machine": ""}, "machine"),
        ({"ts": "ieri"}, "ts"),
        ({"ts": "2026-10-22T08:00:00"}, "ts"),
        ({"unit": 5}, "unit"),
    ],
    ids=[
        "lipsa-value",
        "lipsa-machine",
        "value-text",
        "value-bool",
        "machine-gol",
        "ts-invalid",
        "ts-fara-fus",
        "unit-numar",
    ],
)
def test_contract_violations_name_the_field(changes: dict[str, object], field: str) -> None:
    result = validate(_received(_payload(**changes)))
    assert isinstance(result, Rejected)
    assert result.reason == CONTRACT_INVALID
    assert result.detail.startswith(f"{field}:")


def test_unknown_extra_field_is_accepted() -> None:
    # Un producator actualizat inaintea consumatorilor nu ajunge in carantina (ADR-021).
    assert isinstance(validate(_received(_payload(firmware="2.1"))), Reading)


def test_integer_value_is_accepted() -> None:
    assert isinstance(validate(_received(_payload(value=65))), Reading)


def test_bridge_payload_follows_contract() -> None:
    # Testul de contract: ce produce bridge-ul trebuie sa treaca de modelul consumatorului.
    for machine in MACHINES:
        for sensor in machine.sensors:
            payload = payload_for(machine.name, sensor.name, 1.0, sensor.unit, WHEN)
            assert isinstance(validate(_received(payload)), Reading)


# --- fereastra de timp ---------------------------------------------------------------------


def _at(ts: datetime) -> Received:
    return _received(payload_for("motor", "temperatura", 65.0, "C", ts))


@pytest.mark.parametrize(
    ("offset", "reason"),
    [
        (timedelta(seconds=60), None),
        (timedelta(seconds=61), TS_AHEAD),
        (timedelta(hours=1), TS_AHEAD),
        (-timedelta(days=7), None),
        (-timedelta(days=7, seconds=1), TS_TOO_OLD),
    ],
    ids=["60s-viitor", "61s-viitor", "1h-viitor", "7-zile", "peste-7-zile"],
)
def test_time_window_is_measured_from_arrival(offset: timedelta, reason: str | None) -> None:
    assert _reason(_at(WHEN + offset)) == reason


def test_verdict_does_not_depend_on_current_clock() -> None:
    # Reprocesarea din bronze peste o luna da acelasi verdict: fereastra e fata de sosire,
    # iar sosirea e salvata in mesaj, nu luata din ceasul curent.
    message = _at(WHEN - timedelta(days=1))
    assert isinstance(validate(message), Reading)
    replayed = Received(message.topic, message.payload, 99, 1, message.ingestion_ts)
    assert isinstance(validate(replayed), Reading)


# --- reguli de valoare (FP-204) ------------------------------------------------------------


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
    # json.dumps scrie NaN/Infinity ca token-uri nestandard; json.loads si pydantic le accepta,
    # deci respingerea vine din regula de valoare, cu motivul ei.
    payload = _payload(value=0).replace('"value": 0', f'"value": {token}')
    assert _reason(_received(payload)) == VALUE_NOT_FINITE


def test_unknown_unit() -> None:
    assert _reason(_reading(65.0, "F")) == UNKNOWN_UNIT


@pytest.mark.parametrize("payload", ["nu e json", "[1, 2, 3]", "65.1"])
def test_unreadable_payload(payload: str) -> None:
    assert _reason(_received(payload)) == PAYLOAD_INVALID


def test_non_utf8_payload() -> None:
    message = Received("factory/motor/temperatura", b"\xff\xfe", 1, 1, WHEN)
    assert _reason(message) == PAYLOAD_INVALID


def test_late_and_out_of_order_data_is_accepted() -> None:
    # ADR-021: ordinea se stabileste dupa ts, nu dupa sosire.
    assert isinstance(validate(_at(WHEN - timedelta(hours=6))), Reading)


def test_every_simulated_unit_has_limits() -> None:
    units = {sensor.unit for machine in MACHINES for sensor in machine.sensors}
    assert units <= set(LIMITS)
