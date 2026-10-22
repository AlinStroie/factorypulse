"""Validarea de baza a mesajelor: ce e valid ajunge in `telemetry`, restul in carantina.

Limitele sunt fizic plauzibile, nu intervalul normal de functionare: o supraincalzire reala
e o anomalie (de detectat in Sprintul 4), nu o eroare de date, deci trebuie sa treaca.
Se resping doar valorile pe care niciun senzor functional nu le-ar putea trimite.

Datele intarziate sau sosite in alta ordine se accepta (ADR-021). Regulile contractului v1
(versiune, fereastra de timp) vin in FP-208, in aceeasi functie.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from factorypulse.ingestor.batch import Reading, Received, parse

# Coduri stabile: apar in rapoarte si in metrici (FP-209); textul liber e in `detail`.
PAYLOAD_INVALID = "payload_invalid"
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


def validate(message: Received) -> Reading | Rejected:
    try:
        reading = parse(message)
    except ValueError as exc:
        return Rejected(message, PAYLOAD_INVALID, str(exc))

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
