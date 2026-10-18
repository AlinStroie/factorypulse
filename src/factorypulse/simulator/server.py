"""Server OPC UA care expune senzorii simulati ai fabricii."""

from __future__ import annotations

import asyncio
import time

from asyncua.server.server import Server

from factorypulse.simulator.model import MACHINES, SignalGenerator

NAMESPACE_URI = "urn:factorypulse:simulator"


async def run(endpoint: str, interval_s: float, seed: int) -> None:
    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name("FactoryPulse Simulator")

    idx = await server.register_namespace(NAMESPACE_URI)
    factory = await server.nodes.objects.add_object(idx, "Factory")

    nodes = {}
    for machine in MACHINES:
        machine_node = await factory.add_object(idx, machine.name)
        for sensor in machine.sensors:
            nodes[(machine.name, sensor.name)] = await machine_node.add_variable(
                idx, sensor.name, 0.0
            )

    generator = SignalGenerator(seed=seed)
    start = time.monotonic()

    async with server:
        while True:
            t = time.monotonic() - start
            for machine in MACHINES:
                for sensor in machine.sensors:
                    value = generator.sample(machine, sensor, t)
                    await nodes[(machine.name, sensor.name)].write_value(value)
            await asyncio.sleep(interval_s)


if __name__ == "__main__":
    asyncio.run(run("opc.tcp://0.0.0.0:4840/factorypulse/server/", 1.0, 42))
