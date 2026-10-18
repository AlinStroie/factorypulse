"""Teste pentru maparea topicurilor si a payload-urilor MQTT."""

import json
from datetime import UTC, datetime

from factorypulse.bridge.mapping import payload_for, topic_for


def test_topic_follows_factory_machine_sensor_pattern() -> None:
    assert topic_for("motor", "temperatura") == "factory/motor/temperatura"


def test_payload_contains_timestamp_value_and_unit() -> None:
    when = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    data = json.loads(payload_for(64.123456, "C", when))
    assert data == {"ts": "2026-10-18T12:00:00+00:00", "value": 64.1235, "unit": "C"}
