"""Bridge: citeste senzorii din serverul OPC UA si publica pe MQTT."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import paho.mqtt.client as mqtt
from asyncua.client.client import Client
from asyncua.common.node import Node
from paho.mqtt.enums import CallbackAPIVersion

from factorypulse.bridge.mapping import payload_for, topic_for
from factorypulse.simulator.model import MACHINES
from factorypulse.simulator.server import NAMESPACE_URI


async def run(opcua_url: str, mqtt_host: str, mqtt_port: int, interval_s: float) -> None:
    mqtt_client = mqtt.Client(CallbackAPIVersion.VERSION2)
    mqtt_client.connect(mqtt_host, mqtt_port)
    mqtt_client.loop_start()

    async with Client(opcua_url) as opc:
        ns = await opc.get_namespace_index(NAMESPACE_URI)
        factory = await opc.nodes.objects.get_child([f"{ns}:Factory"])

        sensors: list[tuple[str, str, str, Node]] = []
        for machine_spec in MACHINES:
            machine_node = await factory.get_child([f"{ns}:{machine_spec.name}"])
            for sensor_spec in machine_spec.sensors:
                node = await machine_node.get_child([f"{ns}:{sensor_spec.name}"])
                sensors.append((machine_spec.name, sensor_spec.name, sensor_spec.unit, node))

        try:
            while True:
                now = datetime.now(UTC)
                values = await opc.read_values([node for *_, node in sensors])
                for (machine, sensor, unit, _), value in zip(sensors, values, strict=True):
                    mqtt_client.publish(
                        topic_for(machine, sensor),
                        payload_for(float(value), unit, now),
                        qos=1,
                    )
                await asyncio.sleep(interval_s)
        finally:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    asyncio.run(run("opc.tcp://127.0.0.1:4840/factorypulse/server/", "127.0.0.1", 1883, 1.0))
