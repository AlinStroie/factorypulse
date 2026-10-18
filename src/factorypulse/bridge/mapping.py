"""Mapare intre senzori OPC UA si topicuri/payload-uri MQTT."""

from __future__ import annotations

import json
from datetime import UTC, datetime


def topic_for(machine: str, sensor: str) -> str:
    return f"factory/{machine}/{sensor}"


def payload_for(value: float, unit: str, when: datetime | None = None) -> str:
    ts = (when or datetime.now(UTC)).isoformat()
    return json.dumps({"ts": ts, "value": round(value, 4), "unit": unit}, ensure_ascii=False)
