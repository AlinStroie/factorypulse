"""Validarea mesajelor: ce e valid ajunge in `telemetry`, restul in carantina.

Ordinea regulilor: JSON citibil, versiunea contractului, contractul v1 (ADR-021, FP-208),
fereastra de timp, apoi regulile de valoare (FP-204).

Limitele sunt fizic plauzibile, nu intervalul normal de functionare: o supraincalzire reala
e o anomalie (de detectat in Sprintul 4), nu o eroare de date, deci trebuie sa treaca.
Se resping doar valorile pe care niciun senzor functional nu le-ar putea trimite.

Datele intarziate sau sosite in alta ordine se accepta (ADR-021), cat timp sunt in fereastra.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from pydantic import ValidationError

from factorypulse.contract import MAX_AGE, MAX_AHEAD, SUPPORTED_VERSIONS, TelemetryV1
from factorypulse.ingestor.batch import Reading, Received

# Coduri stabile: apar in rapoarte si in metrici (FP-209); textul liber e in `detail`.
PAYLOAD_INVALID = "payload_invalid"
UNSUPPORTED_VERSION = "versiune_nesuportata"
CONTRACT_INVALID = "contract_invalid"
TS_AHEAD = "ts_in_viitor"
TS_TOO_OLD = "ts_prea_vechi"
VALUE_NOT_FINITE = "valoare_nefinita"
UNKNOWN_UNIT = "unitate_necunoscuta"
OUT_OF_LIMITS = "in_afara_limitelor"

# Limite fizice pe unitate de masura (inclusiv capetele).
LIMITS: dict[str, tuple[float, float]] = {
    "C": (-50.0, 250.0),
    "bar": (0.0, 50.0),
    "mm/s": (0.0, 100.0),
    "A": (0.0, 500.0),
    "rpm": (0.0, 10_000.0),
    "l/min": (0.0, 2_000.0),
}


@dataclass(frozen=True)
class Rejected:
    message: Received
    reason: str
    detail: str


def _contract_errors(exc: ValidationError) -> str:
    """Primele erori, cu numele campului: `value: Input should be a valid number`."""
    parts = [
        f"{'.'.join(str(p) for p in err['loc']) or 'payload'}: {err['msg']}"
        for err in exc.errors()[:3]
    ]
    return "; ".join(parts)


def validate(message: Received) -> Reading | Rejected:
    try:
        data = json.loads(message.payload)
    except ValueError as exc:  # include UnicodeDecodeError
        return Rejected(message, PAYLOAD_INVALID, f"payload invalid: {exc}")
    if not isinstance(data, dict):
        return Rejected(message, PAYLOAD_INVALID, "payload invalid: nu e obiect JSON")

    # Versiunea separat de restul contractului, ca motivul sa fie clar. In Python
    # `True == 1`, deci tipul se verifica explicit.
    version = data.get("schema_version")
    if type(version) is not int or version not in SUPPORTED_VERSIONS:
        accepted = ", ".join(str(v) for v in sorted(SUPPORTED_VERSIONS))
        detail = f"schema_version={version!r}, acceptat: {accepted}"
        return Rejected(message, UNSUPPORTED_VERSION, detail)

    try:
        payload = TelemetryV1.model_validate_json(message.payload)
    except ValidationError as exc:
        return Rejected(message, CONTRACT_INVALID, _contract_errors(exc))

    ahead = payload.ts - message.ingestion_ts
    if ahead > MAX_AHEAD:
        detail = f"ts cu {ahead.total_seconds():.0f} s dupa sosire, maxim {MAX_AHEAD.seconds} s"
        return Rejected(message, TS_AHEAD, detail)
    if -ahead > MAX_AGE:
        days = -ahead.total_seconds() / 86_400
        detail = f"ts cu {days:.1f} zile inainte de sosire, maxim {MAX_AGE.days} zile"
        return Rejected(message, TS_TOO_OLD, detail)

    reading = Reading(
        machine=payload.machine,
        sensor=payload.sensor,
        ts=payload.ts,
        value=payload.value,
        unit=payload.unit,
        ingestion_ts=message.ingestion_ts,
    )
    what = f"{reading.machine}/{reading.sensor}={reading.value} {reading.unit}"
    if not math.isfinite(reading.value):
        return Rejected(message, VALUE_NOT_FINITE, what)
    limits = LIMITS.get(reading.unit)
    if limits is None:
        return Rejected(message, UNKNOWN_UNIT, what)
    low, high = limits
    if not low <= reading.value <= high:
        return Rejected(message, OUT_OF_LIMITS, f"{what}, limite {low:g}..{high:g}")
    return reading
