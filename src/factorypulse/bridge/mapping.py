"""Mapare intre senzori OPC UA si topicuri/payload-uri MQTT.

Contractul mesajului e descris in docs/adr/ADR-021-contract-mesaje-timp.md.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

SCHEMA_VERSION = 1


def topic_for(machine: str, sensor: str) -> str:
    return f"factory/{machine}/{sensor}"


def payload_for(
    machine: str, sensor: str, value: float, unit: str, when: datetime | None = None
) -> str:
    """Payload JSON. `ts` e momentul masurarii (SourceTimestamp), mereu in UTC."""
    moment = when or datetime.now(UTC)
    if moment.tzinfo is None:
        # asyncua intoarce uneori datetime naiv; valorile OPC UA sunt in UTC prin standard
        moment = moment.replace(tzinfo=UTC)
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "machine": machine,
            "sensor": sensor,
            "ts": moment.astimezone(UTC).isoformat(),
            "value": round(value, 4),
            "unit": unit,
        },
        ensure_ascii=False,
    )
