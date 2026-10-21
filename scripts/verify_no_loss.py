"""Verifica AC-ul FP-201: niciun mesaj publicat nu lipseste din TimescaleDB.

Un subscriber independent asculta `factory/#` cat timp ruleaza testul si retine fiecare
(masina, senzor, ts). La final, cauta aceleasi chei in tabelul `telemetry`.

Rulare (cu docker compose pornit si variabilele din .env exportate):
    python scripts/verify_no_loss.py --minutes 10

In timpul testului poti opri ingestorul sau baza de date, ca sa vezi ca nu se pierde nimic:
    docker compose restart ingestor
    docker compose stop timescaledb; sleep 30; docker compose start timescaledb
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime

import paho.mqtt.client as mqtt
import psycopg
from paho.mqtt.enums import CallbackAPIVersion
from psycopg.conninfo import make_conninfo

Key = tuple[str, str, datetime]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--settle-s", type=float, default=10.0, help="asteptare pentru ultimul lot")
    args = parser.parse_args()

    seen: set[Key] = set()
    lock = threading.Lock()

    def on_message(client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
        data = json.loads(msg.payload)
        with lock:
            seen.add((data["machine"], data["sensor"], datetime.fromisoformat(data["ts"])))

    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="factorypulse-verify")
    client.on_message = on_message
    client.connect(os.getenv("MQTT_HOST", "127.0.0.1"), int(os.getenv("MQTT_PORT", "1883")))
    client.subscribe("factory/#", qos=1)
    client.loop_start()
    print(f"ascult {args.minutes} minute...")
    time.sleep(args.minutes * 60)
    client.loop_stop()
    client.disconnect()

    print(f"astept {args.settle_s} s ca ingestorul sa scrie ultimul lot...")
    time.sleep(args.settle_s)

    with lock:
        expected = set(seen)
    if not expected:
        print("niciun mesaj primit; bridge-ul ruleaza?")
        return 1
    first, last = min(k[2] for k in expected), max(k[2] for k in expected)

    conninfo = make_conninfo(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        user=os.getenv("POSTGRES_USER", "factory"),
        password=os.getenv("POSTGRES_PASSWORD"),
        dbname=os.getenv("POSTGRES_DB", "factorypulse"),
    )
    with psycopg.connect(conninfo) as conn:
        rows = conn.execute(
            "SELECT machine, sensor, ts FROM telemetry WHERE ts BETWEEN %s AND %s",
            (first, last),
        ).fetchall()
    stored: list[Key] = [(m, s, ts) for m, s, ts in rows]
    missing = expected - set(stored)

    print(f"interval: {first.isoformat()} .. {last.isoformat()}")
    print(f"mesaje publicate (vazute de subscriber): {len(expected)}")
    print(f"randuri in telemetry:                   {len(stored)}")
    print(f"lipsa din telemetry:                    {len(missing)}")
    print(f"duplicate (rezolvate in FP-202):        {len(stored) - len(set(stored))}")
    # Primul ciclu al bridge-ului poate fi prins doar partial: senzorii publicati inainte
    # de abonare au acelasi ts si apar in baza, dar nu la subscriber. Nu e o eroare.
    print(f"in telemetry, publicate inainte de abonare: {len(set(stored) - expected)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
