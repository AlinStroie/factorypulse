# FactoryPulse

Platforma de date industriale: ingestie OPC UA/MQTT, calitatea datelor, detectie de anomalii, agent RCA.

Status: in dezvoltare (Sprint 1).

Plan: [docs/PLAN_PROIECT.md](docs/PLAN_PROIECT.md). Workflow: [docs/WORKFLOW.md](docs/WORKFLOW.md). Decizii: [docs/adr/](docs/adr/).

## Rulare locala

```bash
cp .env.example .env          # completeaza parolele
docker compose up -d --build  # EMQX, TimescaleDB, Grafana, simulator, bridge
```

- EMQX dashboard: http://localhost:18083 (topic `factory/#`)
- Grafana: http://localhost:3000 (sursa TimescaleDB e provizionata automat)
- Etichetele de adevar: `data/ground_truth/ground_truth_<pornire>.json`, cate una per rulare

Verificari: `make check` (Linux/CI) sau `powershell -File scripts/check.ps1` (Windows).
