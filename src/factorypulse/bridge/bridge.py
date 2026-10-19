"""Bridge: citeste senzorii din serverul OPC UA si publica pe MQTT."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import paho.mqtt.client as mqtt
from asyncua import ua
from asyncua.client.client import Client
from asyncua.common.node import Node
from asyncua.ua.uaerrors import UaError
from paho.mqtt.enums import CallbackAPIVersion

from factorypulse.bridge.mapping import payload_for, topic_for
from factorypulse.simulator.model import MACHINES
from factorypulse.simulator.server import NAMESPACE_URI

log = logging.getLogger(__name__)

# Erorile dupa care merita reconectarea la OPC UA (server oprit, retea, timeout).
_RECOVERABLE = (OSError, TimeoutError, ConnectionError, UaError)


@dataclass(frozen=True)
class BridgeConfig:
    opcua_url: str = "opc.tcp://127.0.0.1:4840/factorypulse/server/"
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_client_id: str = "factorypulse-bridge"
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    interval_s: float = 1.0
    max_backoff_s: float = 30.0

    @classmethod
    def from_env(cls) -> BridgeConfig:
        defaults = cls()
        return cls(
            opcua_url=os.getenv("OPCUA_URL", defaults.opcua_url),
            mqtt_host=os.getenv("MQTT_HOST", defaults.mqtt_host),
            mqtt_port=int(os.getenv("MQTT_PORT", str(defaults.mqtt_port))),
            mqtt_client_id=os.getenv("MQTT_CLIENT_ID", defaults.mqtt_client_id),
            mqtt_username=os.getenv("MQTT_USERNAME") or None,
            mqtt_password=os.getenv("MQTT_PASSWORD") or None,
            interval_s=float(os.getenv("BRIDGE_INTERVAL_S", str(defaults.interval_s))),
        )


@dataclass(frozen=True)
class SensorRef:
    machine: str
    sensor: str
    unit: str
    node: Node


class Publisher(Protocol):
    def publish(self, topic: str, payload: str, qos: int) -> Any: ...


def build_messages(
    sensors: Sequence[SensorRef], data_values: Sequence[ua.DataValue]
) -> list[tuple[str, str]]:
    """Transforma citirile OPC UA in (topic, payload). Citirile cu status rau sunt sarite."""
    messages: list[tuple[str, str]] = []
    for ref, dv in zip(sensors, data_values, strict=True):
        status = dv.StatusCode
        if dv.Value is None or (status is not None and not status.is_good()):
            log.warning("citire invalida %s/%s: %s", ref.machine, ref.sensor, status)
            continue
        payload = payload_for(
            ref.machine, ref.sensor, float(dv.Value.Value), ref.unit, dv.SourceTimestamp
        )
        messages.append((topic_for(ref.machine, ref.sensor), payload))
    return messages


async def discover_sensors(opc: Client) -> list[SensorRef]:
    ns = await opc.get_namespace_index(NAMESPACE_URI)
    factory = await opc.nodes.objects.get_child([f"{ns}:Factory"])
    sensors: list[SensorRef] = []
    for machine_spec in MACHINES:
        machine_node = await factory.get_child([f"{ns}:{machine_spec.name}"])
        for sensor_spec in machine_spec.sensors:
            node = await machine_node.get_child([f"{ns}:{sensor_spec.name}"])
            sensors.append(SensorRef(machine_spec.name, sensor_spec.name, sensor_spec.unit, node))
    return sensors


async def poll_once(opc: Client, sensors: Sequence[SensorRef], publisher: Publisher) -> int:
    """O citire batch (un singur request) si publicare. Intoarce numarul de mesaje."""
    data_values = await opc.read_attributes([s.node for s in sensors])
    messages = build_messages(sensors, data_values)
    for topic, payload in messages:
        publisher.publish(topic, payload, qos=1)
    return len(messages)


def make_mqtt_client(config: BridgeConfig) -> mqtt.Client:
    # clean_session=False + client_id fix: brokerul pastreaza sesiunea la reconectare,
    # iar mesajele QoS 1 neconfirmate sunt retrimise.
    client = mqtt.Client(
        CallbackAPIVersion.VERSION2, client_id=config.mqtt_client_id, clean_session=False
    )
    if config.mqtt_username:
        client.username_pw_set(config.mqtt_username, config.mqtt_password)
    client.reconnect_delay_set(min_delay=1, max_delay=int(config.max_backoff_s))
    return client


async def run(config: BridgeConfig) -> None:
    mqtt_client = make_mqtt_client(config)
    # connect_async + loop_start: paho reincearca singur conectarea daca brokerul nu e gata
    mqtt_client.connect_async(config.mqtt_host, config.mqtt_port)
    mqtt_client.loop_start()

    backoff = 1.0
    try:
        while True:
            try:
                async with Client(config.opcua_url) as opc:
                    sensors = await discover_sensors(opc)
                    log.info("conectat la %s, %d senzori", config.opcua_url, len(sensors))
                    backoff = 1.0
                    while True:
                        await poll_once(opc, sensors, mqtt_client)
                        await asyncio.sleep(config.interval_s)
            except _RECOVERABLE as exc:
                log.warning("OPC UA indisponibil (%s), reincerc in %.0f s", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, config.max_backoff_s)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # asyncua logheaza fiecare request la INFO; prea mult zgomot pentru 1 citire/secunda
    logging.getLogger("asyncua").setLevel(logging.WARNING)
    asyncio.run(run(BridgeConfig.from_env()))
