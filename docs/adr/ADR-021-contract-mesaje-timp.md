# ADR-021: Contractul mesajelor MQTT și timpul evenimentului

- **Status:** Accepted
- **Data:** 2026-10-19
- **Completează:** ADR-003 (MQTT cu JSON).

## Context

În v1, payload-ul avea `ts`, `value` și `unit`, iar `ts` era ora la care bridge-ul *citea* valoarea, nu ora măsurării. Eticheta de adevăr avea doar secunde relative la pornirea simulatorului. Telemetria și defectele erau pe ceasuri diferite, deci precision și recall din Sprint 4 nu se puteau calcula corect.

## Decizie

**Payload v1** (`schema_version: 1`), pe topicul `factory/<masina>/<senzor>`:

```json
{
  "schema_version": 1,
  "machine": "motor",
  "sensor": "temperatura",
  "ts": "2026-10-19T08:00:01.000000+00:00",
  "value": 65.1234,
  "unit": "C"
}
```

- `ts` = **timpul evenimentului**, adică `SourceTimestamp` din OPC UA. Mereu ISO 8601 în UTC.
- `machine` și `sensor` se repetă în payload, deși sunt în topic: în bronze, un mesaj trebuie să se poată citi fără topic.
- Ingestorul adaugă `ingestion_ts` (timpul procesării). Diferența `ingestion_ts - ts` e latența pipeline-ului (ADR-022).
- Eticheta de adevăr are `simulation_start` și `start_ts`/`end_ts` absolute. Simulatorul scrie `SourceTimestamp = simulation_start + t`, deci telemetria și eticheta folosesc același ceas.

**Date întârziate sau în altă ordine:** se acceptă. Ordinea se stabilește după `ts`, nu după ordinea de sosire. Mesajele cu `ts` în viitor (mai mult de 60 s) sau mai vechi de 7 zile merg în carantină.

**Evoluție:** o schimbare compatibilă (un câmp nou, opțional) păstrează versiunea. O schimbare incompatibilă crește `schema_version`, iar ingestorul acceptă versiunea curentă și pe cea anterioară cel puțin un sprint.

## Alternative respinse

- **Timestamp la citire (v1 inițial):** ascunde întârzierile reale și strică evaluarea detecției.
- **Avro sau Protobuf cu schema registry:** corect în producție, dar prea greu pentru volumul și echipa noastră. Sparkplug B (ADR-003) rămâne pasul următor dacă e nevoie de payload binar.

## Consecințe

- Ingestorul validează contractul la intrare (FP-208), cu un model pydantic generat din acest ADR.
- Payload-ul crește cu ~40 de octeți. La 13 mesaje pe secundă, diferența e neglijabilă.

## Verificare

- `tests/test_bridge_mapping.py` fixează forma payload-ului v1.
- `tests/test_simulator_server.py` verifică faptul că `SourceTimestamp` e pe același ceas cu `simulation_start`.
