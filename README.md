# FactoryPulse

Platforma de date industriale: ingestie OPC UA/MQTT, calitatea datelor, detectie de anomalii, agent RCA.

Status: in dezvoltare (Sprint 2).

Plan: [docs/PLAN_PROIECT.md](docs/PLAN_PROIECT.md). Workflow: [docs/WORKFLOW.md](docs/WORKFLOW.md). Decizii: [docs/adr/](docs/adr/).

## Rulare locala

```bash
cp .env.example .env          # completeaza parolele
docker compose up -d --build  # EMQX, TimescaleDB, Grafana, simulator, bridge, ingestor
```

- EMQX dashboard: http://localhost:18083 (topic `factory/#`)
- Grafana: http://localhost:3000 (sursa TimescaleDB e provizionata automat)
- Telemetria: tabelul `telemetry` din TimescaleDB, scris de ingestor in loturi (500 de mesaje sau 1 s)
- Bronze: `data/bronze/telemetry/dt=<zi>/`, mesajele brute in Parquet (`pandas.read_parquet("data/bronze/telemetry")`)
- Silver: `python -m factorypulse.silver --from AAAA-LL-ZZ --to AAAA-LL-ZZ` scrie `data/silver/telemetry/date=<zi>/`, curat si deduplicat
- Verificare fara pierderi: `python scripts/verify_no_loss.py --minutes 10`
- Etichetele de adevar: `data/ground_truth/ground_truth_<pornire>.json`, cate una per rulare

Verificari: `make check` (Linux/CI) sau `powershell -File scripts/check.ps1` (Windows).
