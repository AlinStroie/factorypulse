"""Defecte injectate in simulator, cu etichete de adevar (ground truth)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from factorypulse.simulator.model import MACHINES

# Tip de defect -> senzorul afectat si amplitudinea deviatiei (in unitatile senzorului).
FAULT_KINDS: dict[str, tuple[str, float]] = {
    "supraincalzire": ("temperatura", 12.0),
    "crestere_vibratie": ("vibratie", 1.5),
    "scadere_presiune": ("presiune", -1.5),
}


@dataclass(frozen=True)
class Fault:
    machine: str
    sensor: str
    kind: str
    start_s: float
    end_s: float
    magnitude: float

    def offset(self, machine: str, sensor: str, t_seconds: float) -> float:
        if machine != self.machine or sensor != self.sensor:
            return 0.0
        if self.start_s <= t_seconds <= self.end_s:
            return self.magnitude
        return 0.0


class FaultSchedule:
    def __init__(self, faults: list[Fault]) -> None:
        self.faults = list(faults)

    def offset(self, machine: str, sensor: str, t_seconds: float) -> float:
        return sum(f.offset(machine, sensor, t_seconds) for f in self.faults)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(f) for f in self.faults]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> FaultSchedule:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls([Fault(**item) for item in raw])


def random_schedule(seed: int, duration_s: float, count: int = 3) -> FaultSchedule:
    """Genereaza defecte reproductibile, distribuite pe durata data."""
    rng = random.Random(seed)
    faults: list[Fault] = []
    kinds = list(FAULT_KINDS)
    for _ in range(count):
        kind = rng.choice(kinds)
        sensor_name, magnitude = FAULT_KINDS[kind]
        candidates = [
            (m.name, s.name) for m in MACHINES for s in m.sensors if s.name == sensor_name
        ]
        machine_name, _ = rng.choice(candidates)
        length = rng.uniform(120.0, 600.0)
        start = rng.uniform(0.0, max(duration_s - length, 0.0))
        faults.append(
            Fault(
                machine=machine_name,
                sensor=sensor_name,
                kind=kind,
                start_s=round(start, 1),
                end_s=round(start + length, 1),
                magnitude=magnitude,
            )
        )
    faults.sort(key=lambda f: f.start_s)
    return FaultSchedule(faults)
