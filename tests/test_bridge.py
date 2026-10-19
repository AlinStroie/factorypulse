"""Teste pentru bridge: configurare, filtrarea citirilor si un ciclu complet cu serverul."""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from asyncua import ua
from asyncua.common.node import Node
from asyncua.ua.status_codes import StatusCodes
from opcua_helpers import connect_when_ready, running

from factorypulse.bridge.bridge import (
    BridgeConfig,
    SensorRef,
    build_messages,
    discover_sensors,
    make_mqtt_client,
    poll_once,
)
from factorypulse.simulator.model import MACHINES
from factorypulse.simulator.server import run as run_server

ENDPOINT = "opc.tcp://127.0.0.1:48411/factorypulse/test/"
WHEN = datetime(2026, 10, 19, 8, 0, 0, tzinfo=UTC)


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, int]] = []

    def publish(self, topic: str, payload: str, qos: int) -> Any:
        self.messages.append((topic, payload, qos))


def _ref(machine: str, sensor: str) -> SensorRef:
    return SensorRef(machine, sensor, "C", cast(Node, None))


def _dv(value: float, status: int = StatusCodes.Good) -> ua.DataValue:
    return ua.DataValue(
        ua.Variant(value, ua.VariantType.Double),
        StatusCode=ua.StatusCode(ua.UInt32(status)),
        SourceTimestamp=cast(ua.DateTime, WHEN),
    )


def test_config_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MQTT_HOST", "emqx")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.setenv("OPCUA_URL", "opc.tcp://simulator:4840/x/")
    config = BridgeConfig.from_env()
    assert (config.mqtt_host, config.mqtt_port, config.opcua_url) == (
        "emqx",
        8883,
        "opc.tcp://simulator:4840/x/",
    )
    assert config.mqtt_username is None


def test_build_messages_uses_source_timestamp() -> None:
    [(topic, payload)] = build_messages([_ref("motor", "temperatura")], [_dv(65.0)])
    assert topic == "factory/motor/temperatura"
    assert json.loads(payload)["ts"] == WHEN.isoformat()


def test_build_messages_skips_bad_status() -> None:
    refs = [_ref("motor", "temperatura"), _ref("motor", "curent")]
    messages = build_messages(refs, [_dv(1.0, StatusCodes.BadSensorFailure), _dv(2.0)])
    assert [topic for topic, _ in messages] == ["factory/motor/curent"]


async def _one_cycle() -> FakePublisher:
    publisher = FakePublisher()
    async with running(run_server(ENDPOINT, 0.2, 7, duration_s=60.0)):
        opc = await connect_when_ready(ENDPOINT)
        sensors = await discover_sensors(opc)
        await poll_once(opc, sensors, publisher)
        await opc.disconnect()
    return publisher


def test_poll_once_publishes_every_sensor_with_qos1() -> None:
    publisher = asyncio.run(_one_cycle())
    expected = {f"factory/{m.name}/{s.name}" for m in MACHINES for s in m.sensors}
    assert {topic for topic, _, _ in publisher.messages} == expected
    assert all(qos == 1 for _, _, qos in publisher.messages)


def test_mqtt_client_keeps_session_for_qos1() -> None:
    client = make_mqtt_client(BridgeConfig(mqtt_client_id="bridge-test", mqtt_username="u"))
    assert client._client_id == b"bridge-test"
    assert client._clean_session is False
    assert client._username == b"u"
