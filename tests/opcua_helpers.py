"""Utilitare comune pentru testele de integrare cu serverul OPC UA."""

import asyncio
import contextlib
from collections.abc import AsyncIterator, Coroutine
from typing import Any

from asyncua.client.client import Client


@contextlib.asynccontextmanager
async def running(server: Coroutine[Any, Any, None]) -> AsyncIterator[None]:
    """Ruleaza serverul in fundal si il opreste la iesire, fara sa astepte durata lui."""
    task = asyncio.create_task(server)
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def connect_when_ready(endpoint: str, timeout_s: float = 30.0) -> Client:
    """Se conecteaza cand serverul accepta conexiuni (pornirea dureaza mai mult sub coverage)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        client = Client(endpoint)
        try:
            await client.connect()
            return client
        except OSError:
            if loop.time() > deadline:
                raise
            await asyncio.sleep(0.2)
