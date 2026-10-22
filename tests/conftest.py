"""Configurare comuna pentru teste: testele de integrare si schema temporara in Postgres.

Testele de integrare (marcate `integration`) au nevoie de TimescaleDB si EMQX reale:
- local: stack-ul din docker compose, cu FP_TEST_POSTGRES si FP_TEST_MQTT setate;
- in CI: containerele `services` din workflow.

Local sunt optionale (se sar daca variabilele lipsesc). In CI, FP_REQUIRE_INTEGRATION=1
transforma orice test de integrare sarit intr-un esec: un skip ar arata verde fara sa fi
verificat nimic.
"""

from __future__ import annotations

import os
from collections.abc import Generator, Iterator

import psycopg
import pytest

PG_CONNINFO = os.getenv("FP_TEST_POSTGRES")
MQTT_ADDRESS = os.getenv("FP_TEST_MQTT")  # host:port


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, None]:
    outcome = yield
    report = outcome.get_result()
    required = os.getenv("FP_REQUIRE_INTEGRATION") == "1"
    if required and report.skipped and item.get_closest_marker("integration"):
        report.outcome = "failed"
        report.longrepr = (
            "test de integrare sarit, dar FP_REQUIRE_INTEGRATION=1: "
            "verifica FP_TEST_POSTGRES si FP_TEST_MQTT in workflow"
        )


@pytest.fixture
def pg_schema() -> str:
    return f"fp_test_{os.getpid()}"


@pytest.fixture
def pg_conninfo(pg_schema: str) -> Iterator[str]:
    """Conninfo cu search_path pe o schema temporara, stearsa la final.

    Atentie: search_path include si `public` (acolo e extensia timescaledb), deci un nume
    necalificat poate gasi tabelele stack-ului live. Testele care citesc trebuie sa
    califice tabelele cu `pg_schema`.
    """
    if not PG_CONNINFO:
        pytest.skip("FP_TEST_POSTGRES nu e setat")
    schema = pg_schema
    with psycopg.connect(PG_CONNINFO, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        conn.execute(f"CREATE SCHEMA {schema}")
    yield f"{PG_CONNINFO} options='-c search_path={schema},public'"
    with psycopg.connect(PG_CONNINFO, autocommit=True) as conn:
        conn.execute(f"DROP SCHEMA {schema} CASCADE")
