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
| 06 | [`sprint-2/06-grafana-defect-presiune-pompa.png`](sprint-2/06-grafana-defect-presiune-pompa.png) | 2026-10-22 | Rezultat | Primul defect injectat de simulator (`scadere_presiune`, pompa) vizibil în TimescaleDB: presiunea scade de la ~5,9 la ~4,7 bar exact în intervalul din eticheta de adevăr (18:16:48–18:23:31 UTC; graficul e în ora României, 21:16–21:23). Datele de intrare pentru detecția din Sprintul 4 |

### Compactarea bronze pe date reale (FP-203, ADR-025)

Dosarul `data/bronze/telemetry/dt=2026-10-22/`, ora 17 UTC:

| | Înainte (18:00:41 UTC) | După compactare (18:01:11 UTC) |
|---|---|---|
| Fișiere | 1139 (`part-17-*.parquet`, unul per lot) | 1 (`hour-17.parquet`) |
| Dimensiune | 2,6 MB | 316 KB |
| Rânduri | 22 204 | 22 204 |
| Rânduri în `telemetry` pentru aceeași oră | | 22 204 |

Log-ul ingestorului: `compactat .../hour-17.parquet: 1139 fisiere, 22204 randuri`.

### Silver comparat cu TimescaleDB (FP-205)

Silver construit din bronze pentru 22 oct, comparat cu `telemetry` pe același interval de sosire (17:31:25–18:54:51 UTC):

| | Silver | TimescaleDB |
|---|---|---|
| Rânduri | 64 806 | 64 806 |
| Chei comune `(machine, sensor, ts)` | 64 806 | 64 806 |
| Valori diferite | 0 | |
| Duplicate | 0 | 0 |

Două căi de procesare separate (ingestorul în timp real, jobul batch din bronze), aceeași definiție a lui „valid”, același rezultat.

### Carantina pe date reale (FP-204)

Cinci mesaje invalide publicate manual în EMQX, fiecare de două ori (a doua oară simulează o retrimitere de la broker). Tabelul `quarantine`:

| reason | detail |
|---|---|
| `payload_invalid` | payload invalid: Expecting value: line 1 column 1 (char 0) |
| `in_afara_limitelor` | motor/temperatura=-273.0 C, limite -50..250 |
| `in_afara_limitelor` | pompa/presiune=-2.0 bar, limite 0..50 |
| `unitate_necunoscuta` | motor/temperatura=150.0 F |
| `valoare_nefinita` | motor/temperatura=nan C |

5 rânduri, nu 10: retrimiterile nu se dublează. Defectul din captura 06 (presiune ~4,7 bar) a trecut de validare, pentru că e o anomalie reală, nu o eroare de date.
