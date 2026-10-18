"""Model de semnal pentru senzorii simulati: trend, sezonalitate si zgomot."""

from __future__ import annotations

import math
import random
import zlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SensorSpec:
    name: str
    unit: str
    base: float
    trend_per_hour: float
    seasonal_amplitude: float
    period_s: float
    noise_std: float


@dataclass(frozen=True)
class MachineSpec:
    name: str
    sensors: tuple[SensorSpec, ...]


MACHINES: tuple[MachineSpec, ...] = (
    MachineSpec(
        name="motor",
        sensors=(
            SensorSpec("temperatura", "C", 65.0, 0.0, 4.0, 3600.0, 0.8),
            SensorSpec("vibratie", "mm/s", 2.0, 0.0, 0.3, 1800.0, 0.1),
            SensorSpec("turatie", "rpm", 1480.0, 0.0, 15.0, 600.0, 6.0),
            SensorSpec("curent", "A", 12.0, 0.0, 1.0, 3600.0, 0.3),
        ),
    ),
    MachineSpec(
        name="pompa",
        sensors=(
            SensorSpec("presiune", "bar", 6.0, 0.0, 0.4, 900.0, 0.1),
            SensorSpec("debit", "l/min", 120.0, 0.0, 6.0, 3600.0, 1.5),
            SensorSpec("temperatura", "C", 40.0, 0.5, 2.0, 3600.0, 0.5),
            SensorSpec("vibratie", "mm/s", 1.2, 0.0, 0.1, 1800.0, 0.05),
        ),
    ),
    MachineSpec(
        name="compresor",
        sensors=(
            SensorSpec("presiune", "bar", 8.0, 0.0, 0.5, 1200.0, 0.15),
            SensorSpec("temperatura", "C", 75.0, 0.0, 3.0, 3600.0, 1.0),
            SensorSpec("vibratie", "mm/s", 2.5, 0.0, 0.2, 1800.0, 0.1),
            SensorSpec("turatie", "rpm", 2900.0, 0.0, 20.0, 600.0, 8.0),
            SensorSpec("curent", "A", 18.0, 0.0, 1.5, 3600.0, 0.4),
        ),
    ),
)


class SignalGenerator:
    """Genereaza valori deterministe, reproductibile pentru acelasi seed."""

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed
        self._rngs: dict[tuple[str, str], random.Random] = {}

    def _rng(self, machine: str, sensor: str) -> random.Random:
        key = (machine, sensor)
        if key not in self._rngs:
            derived = zlib.crc32(f"{self._seed}/{machine}/{sensor}".encode())
            self._rngs[key] = random.Random(derived)
        return self._rngs[key]

    def sample(self, machine: MachineSpec, sensor: SensorSpec, t_seconds: float) -> float:
        """Valoarea senzorului la momentul t (secunde de la pornire)."""
        trend = sensor.trend_per_hour * (t_seconds / 3600.0)
        seasonal = sensor.seasonal_amplitude * math.sin(2.0 * math.pi * t_seconds / sensor.period_s)
        noise = self._rng(machine.name, sensor.name).gauss(0.0, sensor.noise_std)
        return sensor.base + trend + seasonal + noise
