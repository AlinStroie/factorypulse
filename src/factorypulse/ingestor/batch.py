"""Parsarea mesajelor si gruparea lor in loturi. Fara retea, ca sa se poata testa direct."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Received:
    """Un mesaj MQTT asa cum a venit. `mid` si `qos` sunt necesare pentru ack-ul manual."""

    topic: str
    payload: bytes
    mid: int
    qos: int
    ingestion_ts: datetime


@dataclass(frozen=True)
class Reading:
    machine: str
    sensor: str
    ts: datetime
    value: float
    unit: str
    ingestion_ts: datetime


def parse(message: Received) -> Reading:
    """Payload v1 (ADR-021) -> Reading. Ridica ValueError daca mesajul nu se poate citi.

    Validarea completa a contractului (versiune, fereastra de timp) e in FP-208.
    """
    try:
        data = json.loads(message.payload)
        ts = datetime.fromisoformat(data["ts"])
        reading = Reading(
            machine=str(data["machine"]),
            sensor=str(data["sensor"]),
            ts=ts,
            value=float(data["value"]),
            unit=str(data["unit"]),
            ingestion_ts=message.ingestion_ts,
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"payload invalid: {exc}") from exc
    if ts.tzinfo is None:
        raise ValueError("payload invalid: ts fara fus orar")
    return reading


@dataclass
class Batch:
    """Strange mesaje pana la `max_size` sau pana trec `max_wait_s` de la primul mesaj."""

    max_size: int
    max_wait_s: float
    items: list[Received] = field(default_factory=list)
    # Lotul a ajuns deja in bronze: la reincercare (baza de date cazuta) nu se rescrie.
    bronze_written: bool = False
    _started_at: float | None = None

    def add(self, item: Received, now: float) -> None:
        if not self.items:
            self._started_at = now
        self.items.append(item)

    def is_due(self, now: float) -> bool:
        if not self.items:
            return False
        assert self._started_at is not None
        return len(self.items) >= self.max_size or now - self._started_at >= self.max_wait_s

    def seconds_left(self, now: float) -> float:
        """Cat poate astepta bucla principala dupa urmatorul mesaj inainte de flush."""
        if self._started_at is None or not self.items:
            return self.max_wait_s
        return max(0.0, self.max_wait_s - (now - self._started_at))

    def take(self) -> list[Received]:
        items, self.items, self._started_at = self.items, [], None
        self.bronze_written = False
        return items


def now_utc() -> datetime:
    return datetime.now(UTC)
