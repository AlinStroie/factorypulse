"""Test de integrare: serverul OPC UA porneste, expune senzorii si scrie eticheta de adevar."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from asyncua.client.client import Client

from factorypulse.simulator.faults import Fault, FaultSchedule
from factorypulse.simulator.model import MACHINES
from factorypulse.simulator.server import NAMESPACE_URI, run

ENDPOINT = "opc.tcp://127.0.0.1:48410/factorypulse/test/"


async def _read_while_running(ground_truth: Path) -> list[tuple[float, datetime]]:
    schedule = FaultSchedule([Fault("motor", "temperatura", "supraincalzire", 0.0, 60.0, 12.0)])
    server = asyncio.create_task(
        run(ENDPOINT, 0.2, 42, faults=schedule, duration_s=4.0, ground_truth_path=ground_truth)
    )
    await asyncio.sleep(1.5)
    async with Client(ENDPOINT) as client:
        ns = await client.get_namespace_index(NAMESPACE_URI)
        factory = await client.nodes.objects.get_child([f"{ns}:Factory"])
        nodes = []
        for machine in MACHINES:
            machine_node = await factory.get_child([f"{ns}:{machine.name}"])
            for sensor in machine.sensors:
                nodes.append(await machine_node.get_child([f"{ns}:{sensor.name}"]))
        data_values = await client.read_attributes(nodes)
    await server
    result: list[tuple[float, datetime]] = []
    for dv in data_values:
        assert dv.Value is not None and dv.SourceTimestamp is not None
        result.append((float(dv.Value.Value), dv.SourceTimestamp))
    return result


def test_server_exposes_all_sensors_with_source_timestamp(tmp_path: Path) -> None:
    before = datetime.now(UTC)
    ground_truth = tmp_path / "ground_truth.json"
    values = asyncio.run(_read_while_running(ground_truth))

    assert len(values) == sum(len(m.sensors) for m in MACHINES)
    started_at = FaultSchedule.load(ground_truth).started_at
    assert started_at is not None
    assert before <= started_at <= before + timedelta(seconds=5)
    for _, source_ts in values:
        ts = source_ts if source_ts.tzinfo else source_ts.replace(tzinfo=UTC)
        assert started_at <= ts <= started_at + timedelta(seconds=5)

    # defectul injectat pe motor/temperatura (primul senzor) ridica valoarea cu ~12 C
    motor_temperature, _ = values[0]
    assert motor_temperature > MACHINES[0].sensors[0].base + 6
