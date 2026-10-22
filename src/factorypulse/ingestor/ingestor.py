"""Ingestor: citeste telemetria din MQTT si o scrie in bronze si in TimescaleDB, pe loturi.

Doua thread-uri:
- thread-ul paho primeste mesajele si le pune intr-o coada (nu face nimic lent);
- bucla principala scoate din coada, strange loturi si le scrie: intai bronze (Parquet),
  apoi baza de date (ADR-020).

Ack-ul catre broker se trimite abia dupa ambele scrieri. Daca procesul cade inainte,
brokerul retrimite mesajele, deci nu se pierd (AC FP-201).
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import paho.mqtt.client as mqtt
import psycopg
from paho.mqtt.client import ConnectFlags, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode
from psycopg.conninfo import make_conninfo

from factorypulse.ingestor.batch import Batch, Reading, Received, now_utc
from factorypulse.ingestor.bronze import BronzeWriter
from factorypulse.ingestor.db import PostgresWriter, WriteResult
from factorypulse.ingestor.validate import Rejected, validate

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestorConfig:
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_client_id: str = "factorypulse-ingestor"
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_topic: str = "factory/#"
    pg_host: str = "127.0.0.1"
    pg_port: int = 5432
    pg_user: str = "factory"
    pg_password: str | None = None
    pg_db: str = "factorypulse"
    # Optiuni libpq, de exemplu `-c search_path=...` (testele de integrare isi aleg schema).
    pg_options: str | None = None
    # Lotul nu poate depasi max_inflight din broker: peste el, brokerul nu mai trimite
    # pana nu primeste ack-uri. In docker-compose.yml, EMQX are max_inflight = 1000.
    batch_size: int = 500
    batch_wait_s: float = 1.0
    max_backoff_s: float = 30.0
    bronze_dir: Path = Path("data/bronze")

    @classmethod
    def from_env(cls) -> IngestorConfig:
        defaults = cls()
        return cls(
            mqtt_host=os.getenv("MQTT_HOST", defaults.mqtt_host),
            mqtt_port=int(os.getenv("MQTT_PORT", str(defaults.mqtt_port))),
            mqtt_client_id=os.getenv("MQTT_CLIENT_ID", defaults.mqtt_client_id),
            mqtt_username=os.getenv("MQTT_USERNAME") or None,
            mqtt_password=os.getenv("MQTT_PASSWORD") or None,
            mqtt_topic=os.getenv("MQTT_TOPIC", defaults.mqtt_topic),
            pg_host=os.getenv("POSTGRES_HOST", defaults.pg_host),
            pg_port=int(os.getenv("POSTGRES_PORT", str(defaults.pg_port))),
            pg_user=os.getenv("POSTGRES_USER", defaults.pg_user),
            pg_password=os.getenv("POSTGRES_PASSWORD") or None,
            pg_db=os.getenv("POSTGRES_DB", defaults.pg_db),
            pg_options=os.getenv("POSTGRES_OPTIONS") or None,
            batch_size=int(os.getenv("INGEST_BATCH_SIZE", str(defaults.batch_size))),
            batch_wait_s=float(os.getenv("INGEST_BATCH_WAIT_S", str(defaults.batch_wait_s))),
            bronze_dir=Path(os.getenv("BRONZE_DIR", str(defaults.bronze_dir))),
        )

    def conninfo(self) -> str:
        # make_conninfo sare peste valorile None, deci parola lipsa nu apare in sir
        return make_conninfo(
            host=self.pg_host,
            port=self.pg_port,
            user=self.pg_user,
            password=self.pg_password,
            dbname=self.pg_db,
            options=self.pg_options,
        )


class Writer(Protocol):
    def write(self, readings: list[Reading], rejected: list[Rejected]) -> WriteResult: ...


class Acker(Protocol):
    def ack(self, mid: int, qos: int) -> Any: ...


class Bronze(Protocol):
    def write(self, items: Sequence[Received]) -> Any: ...

    def compact(self, before: datetime) -> int: ...


# Compactarea unei ore incepe la un minut dupa ce s-a terminat: un lot inceput la 10:59:59
# se scrie pana la 11:00:01, iar fisierul lui trebuie sa intre in compactarea orei 10.
COMPACT_GRACE = timedelta(minutes=1)


class Ingestor:
    """Bucla principala, fara retea proprie: primeste coada si destinatiile din afara."""

    def __init__(
        self,
        inbox: queue.Queue[Received],
        bronze: Bronze,
        writer: Writer,
        acker: Acker,
        batch: Batch,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = now_utc,
    ) -> None:
        self._inbox = inbox
        self._bronze = bronze
        self._writer = writer
        self._acker = acker
        self._batch = batch
        self._clock = clock
        self._wall_clock = wall_clock
        self._compacted_until: datetime | None = None

    def step(self) -> int:
        """Asteapta cel mult cat mai are lotul curent, apoi scrie lotul daca e gata.

        Intoarce numarul de randuri noi scrise (0 daca lotul nu era gata).
        """
        try:
            item = self._inbox.get(timeout=self._batch.seconds_left(self._clock()))
        except queue.Empty:
            pass
        else:
            self._batch.add(item, self._clock())
        written = self.flush() if self._batch.is_due(self._clock()) else 0
        self.compact_if_due()
        return written

    def flush_pending(self) -> int:
        """La oprire: scrie lotul inceput, ca mesajele lui sa nu astepte retrimiterea."""
        return self.flush() if self._batch.items else 0

    def compact_if_due(self) -> None:
        """O data pe ora (si la pornire), compacteaza orele terminate din bronze."""
        until = (self._wall_clock() - COMPACT_GRACE).replace(minute=0, second=0, microsecond=0)
        if until == self._compacted_until:
            return
        self._compacted_until = until
        try:
            self._bronze.compact(before=until)
        except OSError as exc:
            # Fisierele mici raman pe disc si intra in compactarea de ora viitoare.
            log.warning("compactarea bronze a esuat: %s", exc)

    def flush(self) -> int:
        """Scrie lotul curent, apoi da ack. Daca scrierea esueaza, lotul ramane si se reincearca."""
        items = self._batch.items
        readings: list[Reading] = []
        rejected: list[Rejected] = []
        for item in items:
            result = validate(item)
            if isinstance(result, Rejected):
                rejected.append(result)
            else:
                readings.append(result)
        # Bronze primeste tot lotul, inclusiv mesajele invalide, si inaintea bazei de date:
        # daca baza cade, datele se pot reincarca din bronze (ADR-020).
        if not self._batch.bronze_written:
            self._bronze.write(items)
            self._batch.bronze_written = True
        # Mesajele respinse merg in carantina in aceeasi tranzactie si se confirma si ele;
        # altfel brokerul le-ar retrimite la nesfarsit.
        written = self._writer.write(readings, rejected)
        if written.rows < len(readings):
            # Normal dupa o repornire: brokerul retrimite mesajele scrise, dar neconfirmate.
            log.info("%d randuri existau deja (FP-202)", len(readings) - written.rows)
        for r in rejected:
            log.warning("carantina %s: %s", r.reason, r.detail)
        for item in items:
            self._acker.ack(item.mid, item.qos)
        self._batch.take()
        return written.rows


def make_mqtt_client(config: IngestorConfig, inbox: queue.Queue[Received]) -> mqtt.Client:
    # manual_ack: paho nu mai confirma singur mesajele; le confirmam noi, dupa commit.
    # clean_session=False + client_id fix: brokerul pastreaza abonamentul si mesajele
    # neconfirmate cat timp ingestorul e oprit.
    client = mqtt.Client(
        CallbackAPIVersion.VERSION2,
        client_id=config.mqtt_client_id,
        clean_session=False,
        manual_ack=True,
    )
    if config.mqtt_username:
        client.username_pw_set(config.mqtt_username, config.mqtt_password)
    client.reconnect_delay_set(min_delay=1, max_delay=int(config.max_backoff_s))

    def on_connect(
        client: mqtt.Client,
        userdata: Any,
        flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None,
    ) -> None:
        if reason_code.is_failure:
            log.warning("conectare MQTT refuzata: %s", reason_code)
            return
        # Abonarea la fiecare conectare: acopera si cazul in care brokerul a pierdut sesiunea.
        client.subscribe(config.mqtt_topic, qos=1)
        log.info("abonat la %s", config.mqtt_topic)

    def on_message(client: mqtt.Client, userdata: Any, msg: MQTTMessage) -> None:
        inbox.put(Received(msg.topic, msg.payload, msg.mid, msg.qos, now_utc()))

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def run(config: IngestorConfig, stop: threading.Event | None = None) -> None:
    """Bucla ingestorului. Ruleaza pana cand `stop` e setat (sau la nesfarsit, fara `stop`)."""
    stop = stop or threading.Event()
    inbox: queue.Queue[Received] = queue.Queue()
    writer = PostgresWriter(config.conninfo())
    mqtt_client = make_mqtt_client(config, inbox)
    bronze = BronzeWriter(config.bronze_dir)
    batch = Batch(config.batch_size, config.batch_wait_s)
    ingestor = Ingestor(inbox, bronze, writer, mqtt_client, batch)

    mqtt_client.connect_async(config.mqtt_host, config.mqtt_port)
    mqtt_client.loop_start()
    backoff = 1.0
    try:
        while not stop.is_set():
            try:
                written = ingestor.step()
            except (psycopg.Error, OSError) as exc:
                # Lotul ramane in memorie si nu e confirmat. Cat timp baza sau discul sunt
                # indisponibile, brokerul opreste livrarea la max_inflight mesaje neconfirmate.
                log.warning("scriere esuata (%s), reincerc in %.0f s", exc, backoff)
                stop.wait(backoff)
                backoff = min(backoff * 2, config.max_backoff_s)
            else:
                backoff = 1.0
                if written:
                    log.debug("scrise %d randuri", written)
        # Oprire ceruta: lotul inceput se scrie si se confirma inainte de deconectare.
        # Daca scrierea esueaza, mesajele raman neconfirmate si brokerul le retrimite.
        try:
            ingestor.flush_pending()
        except (psycopg.Error, OSError) as exc:
            log.warning("lotul final nu s-a scris (%s); brokerul il va retrimite", exc)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        writer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run(IngestorConfig.from_env())
