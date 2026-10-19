"""Server OPC UA care expune senzorii simulati ai fabricii."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from asyncua import ua
from asyncua.common.node import Node
from asyncua.server.server import Server

from factorypulse.simulator.faults import FaultSchedule, random_schedule
from factorypulse.simulator.model import MACHINES, SignalGenerator

NAMESPACE_URI = "urn:factorypulse:simulator"
DEFAULT_ENDPOINT = "opc.tcp://0.0.0.0:4840/factorypulse/server/"

log = logging.getLogger(__name__)


async def run(
    endpoint: str,
    interval_s: float,
    seed: int,
    faults: FaultSchedule | None = None,
    duration_s: float | None = None,
    ground_truth_path: Path | None = None,
) -> None:
    """Porneste serverul si scrie valori pana la `duration_s` (None = la nesfarsit).

    Fiecare valoare are SourceTimestamp = pornire + t, acelasi ceas ca eticheta de adevar.
    """
    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name("FactoryPulse Simulator")

    idx = await server.register_namespace(NAMESPACE_URI)
    factory = await server.nodes.objects.add_object(idx, "Factory")

    nodes: dict[tuple[str, str], Node] = {}
    for machine in MACHINES:
        machine_node = await factory.add_object(idx, machine.name)
        for sensor in machine.sensors:
            nodes[(machine.name, sensor.name)] = await machine_node.add_variable(
                idx, sensor.name, 0.0
            )

    generator = SignalGenerator(seed=seed)
    schedule = faults or FaultSchedule([])

    async with server:
        started_at = datetime.now(UTC)
        start = time.monotonic()
        schedule.started_at = started_at
        if ground_truth_path is not None:
            schedule.save(ground_truth_path)
        log.info("simulator pornit la %s, %d defecte", started_at.isoformat(), len(schedule.faults))

        while duration_s is None or time.monotonic() - start < duration_s:
            t = time.monotonic() - start
            # ua.DateTime e subclasa de datetime; asyncua accepta datetime la rulare
            source_ts = started_at + timedelta(seconds=t)
            for machine in MACHINES:
                for sensor in machine.sensors:
                    value = generator.sample(machine, sensor, t)
                    value += schedule.offset(machine.name, sensor.name, t)
                    data_value = ua.DataValue(
                        ua.Variant(value, ua.VariantType.Double),
                        SourceTimestamp=cast(ua.DateTime, source_ts),
                    )
                    await nodes[(machine.name, sensor.name)].write_value(data_value)
            await asyncio.sleep(interval_s)
        log.info("simulator oprit dupa %.0f s", time.monotonic() - start)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulator OPC UA FactoryPulse")
    parser.add_argument("--endpoint", default=os.getenv("SIM_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument("--interval-s", type=float, default=float(os.getenv("SIM_INTERVAL_S", "1")))
    parser.add_argument("--seed", type=int, default=int(os.getenv("SIM_SEED", "42")))
    parser.add_argument(
        "--duration-s",
        type=float,
        default=float(os.getenv("SIM_DURATION_S", "3600")),
        help="durata simularii; defectele sunt distribuite pe toata durata",
    )
    parser.add_argument("--faults", type=int, default=int(os.getenv("SIM_FAULTS", "3")))
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path(os.getenv("SIM_GROUND_TRUTH", "data/ground_truth.json")),
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    args = _parse_args()
    schedule = random_schedule(seed=args.seed, duration_s=args.duration_s, count=args.faults)
    asyncio.run(
        run(
            args.endpoint,
            args.interval_s,
            args.seed,
            faults=schedule,
            duration_s=args.duration_s,
            ground_truth_path=args.ground_truth,
        )
    )
