# Capturi de ecran

Dovezi vizuale pentru documentul final de proces (WORKFLOW §11): ce arată fiecare captură și la ce etapă din proces aparține. Rezultatele numerice (teste, verificări) rămân text în journal și în PR-uri, unde se pot căuta și compara.

Reguli:
- un dosar per sprint, fișiere numerotate în ordinea procesului (`01-...png` sau `.jpg`);
- fiecare captură are aici data, etapa și ce dovedește;
- nicio parolă, token sau date personale în imagine (repo-ul e public).

## Sprint 2: ingestie și strat bronze

| # | Fișier | Data | Etapa | Ce dovedește |
|---|---|---|---|---|
| 01 | [`sprint-2/01-board-sprint-2.jpg`](sprint-2/01-board-sprint-2.jpg) | 2026-10-22 | Planificare | Backlog-ul Sprintului 2 în Azure Boards: FP-201 și FP-202 închise, FP-203 activ, restul în așteptare; ore rămase pe task-uri |
| 02 | [`sprint-2/02-github-pr-uri-ci-verde.png`](sprint-2/02-github-pr-uri-ci-verde.png) | 2026-10-22 | Livrare | Un PR per tichet, legat cu `AB#`, Conventional Commits, CI verde, squash merge |
| 03 | [`sprint-2/03-emqx-clienti.png`](sprint-2/03-emqx-clienti.png) | 2026-10-22 | Rulare | Bridge-ul și ingestorul conectați la EMQX, cu `Clean Session = false` (sesiune persistentă) |
| 04 | [`sprint-2/04-emqx-ingestor-sesiune.png`](sprint-2/04-emqx-ingestor-sesiune.png) | 2026-10-22 | Rulare | Sesiunea ingestorului: inflight 13/1000 și coada 0/100000, adică setările din `docker-compose.yml` (FP-201) |
| 05 | [`sprint-2/05-grafana-telemetrie-timescaledb.png`](sprint-2/05-grafana-telemetrie-timescaledb.png) | 2026-10-22 | Rezultat | Telemetria scrisă de ingestor în TimescaleDB, interogată din Grafana (temperatura pe mașină, medie pe 5 s) |

### Compactarea bronze pe date reale (FP-203, ADR-025)

Dosarul `data/bronze/telemetry/dt=2026-10-22/`, ora 17 UTC:

| | Înainte (18:00:41 UTC) | După compactare (18:01:11 UTC) |
|---|---|---|
| Fișiere | 1139 (`part-17-*.parquet`, unul per lot) | 1 (`hour-17.parquet`) |
| Dimensiune | 2,6 MB | 316 KB |
| Rânduri | 22 204 | 22 204 |
| Rânduri în `telemetry` pentru aceeași oră | | 22 204 |

Log-ul ingestorului: `compactat .../hour-17.parquet: 1139 fisiere, 22204 randuri`.
