"""Defecte injectate in simulator, cu etichete de adevar (ground truth)."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from factorypulse.simulator.model import MACHINES

# Tip de defect -> senzorul afectat si amplitudinea deviatiei (in unitatile senzorului).
FAULT_KINDS: dict[str, tuple[str, float]] = {
    "supraincalzire": ("temperatura", 12.0),
    "crestere_vibratie": ("vibratie", 1.5),
    "scadere_presiune": ("presiune", -1.5),
}

# Incercari maxime de a plasa un defect fara suprapunere pe acelasi senzor.
_MAX_PLACEMENT_ATTEMPTS = 50


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

    def overlaps(self, other: Fault) -> bool:
        same_target = (self.machine, self.sensor) == (other.machine, other.sensor)
        return same_target and self.start_s <= other.end_s and other.start_s <= self.end_s


class FaultSchedule:
    """Lista de defecte, plus momentul de pornire al simularii (UTC).

    `start_s`/`end_s` sunt relative la pornire. Cu `started_at` setat, eticheta poate fi
    comparata cu telemetria, care are timestamp absolut.
    """

    def __init__(self, faults: list[Fault], started_at: datetime | None = None) -> None:
        self.faults = list(faults)
        self.started_at = started_at

    def offset(self, machine: str, sensor: str, t_seconds: float) -> float:
        return sum(f.offset(machine, sensor, t_seconds) for f in self.faults)

    def save(self, path: Path) -> None:
        if self.started_at is None:
            raise ValueError("started_at lipseste: eticheta nu poate fi legata de telemetrie")
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "simulation_start": self.started_at.isoformat(),
            "faults": [self._fault_record(f, self.started_at) for f in self.faults],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _fault_record(fault: Fault, started_at: datetime) -> dict[str, Any]:
        record: dict[str, Any] = asdict(fault)
        record["start_ts"] = (started_at + timedelta(seconds=fault.start_s)).isoformat()
        record["end_ts"] = (started_at + timedelta(seconds=fault.end_s)).isoformat()
        return record

    @classmethod
    def load(cls, path: Path) -> FaultSchedule:
        raw = json.loads(path.read_text(encoding="utf-8"))
        fields = {"machine", "sensor", "kind", "start_s", "end_s", "magnitude"}
        faults = [Fault(**{k: v for k, v in item.items() if k in fields}) for item in raw["faults"]]
        return cls(faults, started_at=datetime.fromisoformat(raw["simulation_start"]))


def random_schedule(seed: int, duration_s: float, count: int = 3) -> FaultSchedule:
    """Genereaza defecte reproductibile, fara suprapuneri pe acelasi senzor."""
    rng = random.Random(seed)
    faults: list[Fault] = []
    kinds = list(FAULT_KINDS)
    for _ in range(count):
        for _attempt in range(_MAX_PLACEMENT_ATTEMPTS):
            candidate = _random_fault(rng, kinds, duration_s)
            if not any(candidate.overlaps(f) for f in faults):
                faults.append(candidate)
                break
        else:
            raise ValueError(f"nu pot plasa {count} defecte fara suprapunere in {duration_s} s")
    faults.sort(key=lambda f: f.start_s)
    return FaultSchedule(faults)


def _random_fault(rng: random.Random, kinds: list[str], duration_s: float) -> Fault:
    kind = rng.choice(kinds)
    sensor_name, magnitude = FAULT_KINDS[kind]
    candidates = [(m.name, s.name) for m in MACHINES for s in m.sensors if s.name == sensor_name]
    machine_name, _ = rng.choice(candidates)
    length = rng.uniform(120.0, 600.0)
    start = rng.uniform(0.0, max(duration_s - length, 0.0))
    return Fault(
        machine=machine_name,
        sensor=sensor_name,
        kind=kind,
        start_s=round(start, 1),
        end_s=round(start + length, 1),
        magnitude=magnitude,
    )
