"""Contractul mesajelor de telemetrie MQTT (ADR-021).

O singura definitie pentru producator (bridge), ingestor si silver (FP-205), ca sa nu poata
diverge. Schimbarile compatibile (un camp nou, optional) pastreaza versiunea; cele
incompatibile cresc `schema_version`, iar consumatorii accepta versiunea curenta si pe
cea anterioara cel putin un sprint.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

SUPPORTED_VERSIONS: frozenset[int] = frozenset({1})

# Fereastra pentru `ts`, masurata fata de momentul sosirii (`ingestion_ts`), nu fata de
# ceasul curent: la reprocesarea din bronze, acelasi mesaj primeste acelasi verdict.
MAX_AHEAD = timedelta(seconds=60)
MAX_AGE = timedelta(days=7)

NonEmpty = Annotated[str, StringConstraints(min_length=1)]


class TelemetryV1(BaseModel):
    """Payload v1 pe topicul `factory/<masina>/<senzor>`.

    Strict: `"value": "65.1"` (text) sau `true` nu se convertesc in numar. Campurile in
    plus se ignora, ca un producator actualizat inaintea consumatorilor sa nu ajunga in
    carantina.
    """

    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    schema_version: Literal[1]
    machine: NonEmpty
    sensor: NonEmpty
    ts: AwareDatetime  # timpul evenimentului (SourceTimestamp), cu fus orar
    value: float
    unit: NonEmpty
