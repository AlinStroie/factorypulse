"""Teste pentru maparea topicurilor si a payload-urilor MQTT."""

import json
from datetime import UTC, datetime, timedelta, timezone

from factorypulse.bridge.mapping import SCHEMA_VERSION, payload_for, topic_for


def test_topic_follows_factory_machine_sensor_pattern() -> None:
    assert topic_for("motor", "temperatura") == "factory/motor/temperatura"


def test_payload_follows_contract() -> None:
    when = datetime(2026, 10, 18, 12, 0, 0, tzinfo=UTC)
    data = json.loads(payload_for("motor", "temperatura", 64.123456, "C", when))
    assert data == {
        "schema_version": SCHEMA_VERSION,
        "machine": "motor",
        "sensor": "temperatura",
        "ts": "2026-10-18T12:00:00+00:00",
        "value": 64.1235,
        "unit": "C",
    }


def test_naive_timestamp_is_treated_as_utc() -> None:
    data = json.loads(payload_for("motor", "temperatura", 1.0, "C", datetime(2026, 10, 18, 12)))
    assert data["ts"] == "2026-10-18T12:00:00+00:00"


def test_other_timezones_are_converted_to_utc() -> None:
    bucharest = timezone(timedelta(hours=3))
    when = datetime(2026, 10, 18, 15, 0, 0, tzinfo=bucharest)
    data = json.loads(payload_for("motor", "temperatura", 1.0, "C", when))
    assert data["ts"] == "2026-10-18T12:00:00+00:00"
