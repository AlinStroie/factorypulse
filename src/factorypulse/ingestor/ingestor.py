"""Ingestor: citeste telemetria din MQTT si o scrie in TimescaleDB, pe loturi.

Doua thread-uri:
- thread-ul paho primeste mesajele si le pune intr-o coada (nu face nimic lent);
- bucla principala scoate din coada, strange loturi si le scrie in baza de date.

Ack-ul catre broker se trimite abia dupa commit. Daca procesul cade inainte,
brokerul retrimite mesajele, deci nu se pierd (AC FP-201).
"""

from __future__ import annotations

import logging
import os
import queue
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import paho.mqtt.client as mqtt
import psycopg
from paho.mqtt.client import ConnectFlags, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode
from psycopg.conninfo import make_conninfo

from factorypulse.ingestor.batch import Batch, Reading, Received, now_utc, parse
from factorypulse.ingestor.db import PostgresWriter

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
    # Lotul nu poate depasi max_inflight din broker: peste el, brokerul nu mai trimite
    # pana nu primeste ack-uri. In docker-compose.yml, EMQX are max_inflight = 1000.
    batch_size: int = 500
    batch_wait_s: float = 1.0
    max_backoff_s: float = 30.0

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
            batch_size=int(os.getenv("INGEST_BATCH_SIZE", str(defaults.batch_size))),
            batch_wait_s=float(os.getenv("INGEST_BATCH_WAIT_S", str(defaults.batch_wait_s))),
        )

    def conninfo(self) -> str:
        # make_conninfo sare peste valorile None, deci parola lipsa nu apare in sir
        return make_conninfo(
            host=self.pg_host,
            port=self.pg_port,
            user=self.pg_user,
            password=self.pg_password,
            dbname=self.pg_db,
        )


class Writer(Protocol):
    def write(self, readings: list[Reading]) -> None: ...


class Acker(Protocol):
    def ack(self, mid: int, qos: int) -> Any: ...


class Ingestor:
    """Bucla principala, fara retea proprie: primeste coada, writer-ul si acker-ul din afara."""

    def __init__(
        self,
        inbox: queue.Queue[Received],
        writer: Writer,
        acker: Acker,
        batch: Batch,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inbox = inbox
        self._writer = writer
        self._acker = acker
        self._batch = batch
        self._clock = clock

    def step(self) -> int:
        """Asteapta cel mult cat mai are lotul curent, apoi scrie lotul daca e gata.

        Intoarce numarul de randuri scrise (0 daca lotul nu era gata).
        """
        try:
            item = self._inbox.get(timeout=self._batch.seconds_left(self._clock()))
        except queue.Empty:
            pass
        else:
            self._batch.add(item, self._clock())
        if self._batch.is_due(self._clock()):
            return self.flush()
        return 0

    def flush(self) -> int:
        """Scrie lotul curent, apoi da ack. Daca scrierea esueaza, lotul ramane si se reincearca."""
        items = self._batch.items
        readings: list[Reading] = []
        for item in items:
            try:
                readings.append(parse(item))
            except ValueError as exc:
                # Carantina vine in FP-204; pana atunci mesajul e doar logat si confirmat,
                # altfel brokerul l-ar retrimite la nesfarsit.
                log.warning("mesaj ignorat (mid=%d): %s", item.mid, exc)
        # FP-203: bronze (Parquet) se scrie aici, inaintea TimescaleDB (ADR-020).
        self._writer.write(readings)
        for item in items:
            self._acker.ack(item.mid, item.qos)
        self._batch.take()
        return len(readings)


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
        inbox.put(Received(msg.payload, msg.mid, msg.qos, now_utc()))

    client.on_connect = on_connect
    client.on_message = on_message
    return client


def run(config: IngestorConfig) -> None:
    inbox: queue.Queue[Received] = queue.Queue()
    writer = PostgresWriter(config.conninfo())
    mqtt_client = make_mqtt_client(config, inbox)
    ingestor = Ingestor(inbox, writer, mqtt_client, Batch(config.batch_size, config.batch_wait_s))

    mqtt_client.connect_async(config.mqtt_host, config.mqtt_port)
    mqtt_client.loop_start()
    backoff = 1.0
    try:
        while True:
            try:
                written = ingestor.step()
            except psycopg.Error as exc:
                # Lotul ramane in memorie si nu e confirmat. Cat timp baza e cazuta, brokerul
                # opreste livrarea la max_inflight mesaje neconfirmate (presiune inapoi).
                log.warning("TimescaleDB indisponibil (%s), reincerc in %.0f s", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, config.max_backoff_s)
            else:
                if written:
                    backoff = 1.0
                    log.debug("scrise %d randuri", written)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        writer.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    run(IngestorConfig.from_env())
