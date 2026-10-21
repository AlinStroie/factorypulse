# FactoryPulse: plan de proiect (simulare de loc de muncă)

Acest document e planul de referință. Se schimbă doar prin ADR (Architecture Decision Record) nou, nu prin editare directă. Fiecare decizie are motiv, alternative respinse și consecințe.

## 1. Viziune și scop

FactoryPulse e o platformă de date pentru o fabrică: ingestează date de la mașini și din sistemul de mentenanță, validează calitatea, detectează anomalii și ajută inginerii să înțeleagă cauzele defectelor.

**Problemă:** la mentenanța predictivă, calitatea și integrarea datelor limitează rezultatele, mai mult decât senzorii sau algoritmii.

**Utilizatori:**
- inginer de mentenanță: primește alerte și diagnostice
- inginer de date: menține pipeline-ul și calitatea datelor
- manager de producție: vede indicatori și tendințe

**Ce NU e în scope:** control al mașinilor (nu scriem comenzi către PLC), integrare cu ERP real, Sparkplug B în prima versiune, Kubernetes, multi-tenant.

## 2. Reguli de joc (cum lucrăm ca într-o echipă)

- Niciun cod în `main` fără Pull Request și cel puțin o auto-revizuire cu checklist.
- Fiecare ticket are: descriere, criterii de acceptare, estimare, legătură cu un ADR dacă e cazul.
- Niciun ADR nu se modifică după acceptare. Se scrie un ADR nou care îl înlocuiește (ex. „ADR-012 înlocuiește ADR-003”).
- Commituri în stil Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Teste obligatorii pentru logica de business. Coverage țintă: 80% pe `src/`.
- Journal zilnic (`docs/journal/AAAA-LL-ZZ.md`): ce ai făcut, ce ai blocat, ce ai învățat. Asta e materialul pentru interviu.
- Demo la sfârșitul fiecărui sprint, chiar dacă e urât.

## 3. Arhitectura (versiunea 1)

```
EDGE (local, ca o fabrică)                  CLOUD (Azure, ADR-019) / local în dezvoltare
[Simulator OPC UA] --> [Bridge] --> [EMQX] ===> [Ingestor] --1--> [Bronze Parquet, brut]
  SourceTimestamp       contract v1                |                     |
  + ground truth        (ADR-021)                  2 validare            | job batch (Pandas / PySpark)
                                                   v         \           v
                                             [TimescaleDB] [quarantine] [Silver] --> antrenare, eval ML,
                                              (hot, 30 zile)                         raport calitate
                                                   |
                          [Work orders] --> [Detecție anomalii] --> [Alerte]
                                                   |
                        [Grafana] <-- [FastAPI] <--+--> [Agent RCA + Langfuse]
                        + Prometheus: sănătatea pipeline-ului (ADR-022)
```

Regulile fluxului de date (cine scrie unde, care e sursa de adevăr) sunt în ADR-020.

**Straturi:**
- **Sursă:** simulator OPC UA cu mai multe mașini, cu defecte injectate și etichete de adevăr (ground truth).
- **Transport:** MQTT (EMQX Open Source), payload JSON.
- **Stocare:** TimescaleDB pentru telemetrie și alerte, Postgres pentru ordine de lucru, Parquet local pentru bronze/silver/gold.
- **Calitate:** reguli declarative cu pandera, carantină pentru înregistrări invalide.
- **ML:** baseline z-score pe ferestre, Isolation Forest, evaluare pe defectele injectate, MLflow pentru experimente.
- **API:** FastAPI (alerte, mașini, rapoarte).
- **Vizualizare:** Grafana conectat la TimescaleDB.
- **Agent:** unelte peste baza de date și ordinele de lucru, LLM open-weight rulat local (Ollama), trasabilitate cu Langfuse.
- **Observabilitate:** Prometheus și Grafana pentru sănătatea pipeline-ului: prospețime, latență, carantină (ADR-022).
- **Livrare:** Docker Compose local, GitHub Actions pentru CI, Terraform pentru Azure (ADR-017, ADR-019).

## 4. Decizii de arhitectură (ADR)

ADR-001…018 au fost acceptate înainte de Sprintul 1. ADR-019…022 au fost adăugate la revizuirea de la finalul Sprintului 1. Dacă un ADR se schimbă, îl înlocuiești cu unul nou.

| ADR | Decizie | Alternative respinse | Motiv |
|---|---|---|---|
| ADR-001 | Python 3.12, monorepo | Java, microservicii separate | Ecosistem ML și date; un singur repo e suficient pentru o persoană |
| ADR-002 | Sursa de date: OPC UA simulat cu `asyncua`, bridge spre MQTT | Date direct în MQTT | OPC UA e protocolul real din fabrici; bridge-ul arată integrarea |
| ADR-003 | MQTT cu payload JSON în v1, Sparkplug B amânat | Sparkplug B din start | Sparkplug B are complexitate de stare; amânat fără a bloca arhitectura |
| ADR-004 | EMQX Open Source ca broker | HiveMQ Edge, Mosquitto | EMQX are documentație bună și rulează în Docker fără licență |
| ADR-005 | TimescaleDB pentru telemetrie, Postgres pentru restul | InfluxDB, ClickHouse | Un singur motor SQL, familiar pentru echipe; hypertables pentru serii de timp |
| ADR-006 | Parquet local pentru bronze/silver/gold, cu scheme cloud-ready | Doar baza de date | Separă stocarea brută de cea curată, ca în lakehouse; portabil spre ADLS |
| ADR-007 | Pandas/Polars în v1, PySpark ca țintă de scalare documentată | Spark din start | Costuri și complexitate locală; codul e structurat ca să poată fi portat |
| ADR-008 | pandera pentru reguli de calitate | Great Expectations | Mai ușor de citit, reguli ca cod Python; GE e prea greu pentru o persoană |
| ADR-009 | Isolation Forest și z-score, LSTM doar ca extensie | Deep learning din start | Metode interpretabile; baseline-ul trebuie să existe înainte de complexitate |
| ADR-010 | MLflow pentru experimente, local | Weights & Biases | Open source, rulează local, standard în industrie |
| ADR-011 | Grafana pentru dashboard-uri | Streamlit | Potrivit pentru serii de timp și alerte; Streamlit rămâne pentru explorare |
| ADR-012 | Agent RCA cu unelte explicite (tool calling), fără framework greu | LangGraph, LangChain | Control și depanare mai ușoare; framework-urile pot fi adăugate ulterior |
| ADR-013 | LLM open-weight local prin Ollama, API compatibil OpenAI | API comercial | Cost zero în dezvoltare, date care nu părăsesc mașina |
| ADR-014 | Langfuse self-hosted pentru trasabilitate | Fără observabilitate | Fără trace-uri nu poți depana sau măsura agentul |
| ADR-015 | CI cu GitHub Actions: lint, teste, build imagini | Jenkins | Integrat cu repo-ul, fără infrastructură proprie |
| ADR-016 | Terraform pentru Azure, opțional, după MVP | Doar Docker Compose | Arată IaC; nu e necesar pentru funcționare locală |
| ADR-017 | Azure (Container Apps, ADLS Gen2), job Spark și DP-900 devin obligatorii | Doar local; doar Spark; AWS | Cerințele reale din anunțuri. Completează ADR-007 și ADR-016 |
| ADR-018 | Scrum cu Azure DevOps Boards, cod pe GitHub | Doar GitHub Projects; Jira; Azure Repos | Simulare de firmă din ecosistemul Microsoft; repo vizibil pentru recruiteri |
| ADR-019 | Topologie: edge local (simulator, bridge, EMQX), cloud pe Azure (Event Grid MQTT, Container Apps, PostgreSQL Flexible, ADLS, Key Vault) | EMQX în cloud; IoT Hub; ingestor local | Așa arată o fabrică reală; fallback documentat în ADR |
| ADR-020 | Bronze e sursa de adevăr; întâi bronze, apoi TimescaleDB; silver doar din bronze | Doar TimescaleDB; doar Parquet | Reprocesare sigură, o singură sursă de adevăr |
| ADR-021 | Contract de mesaj versionat; `ts` = timpul evenimentului (SourceTimestamp, UTC) | Timestamp la citire; Avro | Telemetria și eticheta de adevăr pe același ceas, ca evaluarea să fie corectă |
| ADR-022 | Observabilitatea pipeline-ului: prospețime, latență, carantină, cu Prometheus și Grafana | OpenTelemetry complet; doar loguri | Incidentul cel mai frecvent („lipsesc date”) trebuie să genereze alertă |

## 5. Sprinturi (2 săptămâni, ~25 ore fiecare)

Ritm: 2,5 ore pe zi, cinci zile pe săptămână. E capacitatea reală din Sprint 1; 35 de ore era o estimare prea optimistă. Ziua 1 a sprintului: planificare. Ultima zi: demo și retrospectivă.

### Sprint 1: Fundație și simulator (săpt. 1-2)
**Obiectiv:** repo funcțional, CI verde, simulatorul publică date prin MQTT.

- FP-101 (chore): structură repo, `pyproject.toml`, ruff, mypy, pytest. AC: `make check` trece.
- FP-102 (chore): Docker Compose cu EMQX, TimescaleDB, Grafana. AC: toate serviciile pornesc cu `docker compose up`.
- FP-103 (docs): ADR-001 până la ADR-016 în `docs/adr/`. AC: fiecare ADR are status „Accepted”.
- FP-104 (feat): simulator OPC UA cu 3 mașini (motor, pompă, compresor), 4-5 senzori fiecare. AC: date realiste (zgomot, trend, sezonalitate).
- FP-105 (feat): injectare de defecte cu etichete de adevăr salvate într-un fișier. AC: fiecare defect are început, sfârșit, tip.
- FP-106 (feat): bridge OPC UA → MQTT. AC: mesajele apar în EMQX cu topic `factory/<masina>/<senzor>`.
- FP-107 (ci): GitHub Actions cu lint și teste. AC: CI verde pe PR.

### Sprint 2: Ingestie și strat brut/curat (săpt. 3-4)
**Obiectiv:** datele ajung în TimescaleDB și în Parquet, cu validare de bază.

- FP-201 (feat): ingestor MQTT → TimescaleDB, cu batch insert. AC: nu pierde mesaje în testul de 10 minute.
- FP-202 (feat): idempotență (cheie unică pe mașină, senzor, timestamp). AC: reprocesarea nu creează duplicate.
- FP-203 (feat): strat bronze în Parquet, partiționat pe zi. AC: fișierele se citesc cu pandas.
- FP-204 (feat): validare de bază (tip, interval, timestamp în ordine) și carantină. AC: înregistrările invalide ajung în tabelul `quarantine`.
- FP-205 (feat): job care construiește silver din bronze. AC: silver are tipuri corecte și fără duplicate.
- FP-206 (test): teste de integrare cu containere. AC: rulează în CI.
- FP-207 (feat, ADR-017, mutat în Sprint 3 la planificare, pentru capacitate): job PySpark bronze → silver. AC: rezultate identice cu varianta Pandas pe același set de date.
- FP-208 (feat, ADR-021): validarea contractului v1 în ingestor (pydantic), cu `ingestion_ts` adăugat. AC: mesajele cu câmpuri lipsă, tipuri greșite sau `ts` în afara ferestrei ajung în carantină, cu motiv.
- FP-209 (feat, ADR-022): metrici Prometheus în ingestor (mesaje, carantină, latență) și Prometheus în compose. AC: metricile apar în Prometheus.

### Sprint 3: Calitate avansată și ordine de lucru (săpt. 5-6)
**Obiectiv:** calitatea datelor e măsurabilă, iar ordinele de lucru sunt integrate.

- FP-301 (feat): reguli declarative cu pandera, versionate. AC: fiecare regulă are test.
- FP-302 (feat): raport de calitate zilnic (procent valide, reguli încălcate, tendințe). AC: raportul e salvat în `reports/`.
- FP-303 (feat): ordine de lucru în Postgres, cu text liber și nume de active. AC: tabelul are chei spre mașini.
- FP-304 (feat): normalizare nume active (ex. „Motor 3”, „M3”, „motor-03” → aceeași mașină). AC: acuratețe de potrivire măsurată pe 50 de exemple etichetate.
- FP-305 (spike): încărcare SCANIA Component X și MetroPT. AC: documentat ce conțin și ce nu conțin, într-un ADR sau în docs.
- FP-306 (feat): loadere pentru dataset-urile publice, care produc același format ca simulatorul. AC: pipeline-ul rulează pe ambele surse.
- FP-310 (feat, ADR-022): dashboard „Pipeline health” și alerte de prospețime, latență și carantină în Grafana. AC: cu bridge-ul oprit 2 minute, alerta de prospețime trece în Firing.
- FP-311 (chore): incident simulat (bridge oprit), cu post-mortem în `docs/incidents/`. AC: post-mortem cu cronologie, cauză, detecție și prevenție.

### Sprint 4: Detecție de anomalii și MVP (săpt. 7-8)
**Obiectiv:** primul MVP demonstrabil. Alerte cu metrici reale.

- FP-401 (feat): baseline z-score pe ferestre glisante. AC: rulează pe toate mașinile.
- FP-402 (feat): Isolation Forest cu features de fereastră. AC: antrenare și scoring reproductibile (seed fix).
- FP-403 (feat): harness de evaluare: precision, recall, întârziere de detecție pe ground truth, potrivite după `start_ts`/`end_ts` absolute (ADR-021). AC: raport generat automat, pe toate fișierele din `data/ground_truth/`.
- FP-404 (feat): experimente în MLflow, comparație baseline vs Isolation Forest. AC: ambele rulări apar în UI.
- FP-405 (feat): tabelul `alerts` și generarea de alerte. AC: alertele au mașină, senzor, scor, timestamp.
- FP-406 (milestone): demo MVP. AC: video scurt cu defect injectat, alertă apărută, metrici.

### Sprint 5: API și vizualizare (săpt. 9-10)
**Obiectiv:** accesul la date și la alerte prin API și dashboard.

- FP-501 (feat): FastAPI cu endpoint-uri pentru mașini, telemetrie agregată, alerte. AC: documentație OpenAPI generată.
- FP-502 (feat): autentificare simplă cu cheie API. AC: endpoint-urile protejate răspund 401 fără cheie.
- FP-503 (feat): dashboard Grafana cu telemetrie, alerte, calitatea datelor. AC: dashboard versionat în repo ca JSON.
- FP-504 (test): teste pentru API. AC: acoperire pe rute critice.
- FP-505 (docs): actualizare arhitectură și README. AC: diagrama reflectă starea reală.

### Sprint 6: Agent RCA (săpt. 11-12)
**Obiectiv:** un agent care propune cauze probabile pentru o alertă, cu dovezi și trasabilitate.

- FP-601 (spike): test cu 2-3 modele open-weight pe Ollama, pe 10 prompturi. AC: alegere justificată în ADR-023.
- FP-602 (feat): unelte: `get_telemetry_window`, `get_recent_work_orders`, `search_similar_alerts`. AC: fiecare unealtă are teste.
- FP-603 (feat): buclă de tool calling cu ieșire structurată (cauză, încredere, dovezi). AC: răspunsul validează schema.
- FP-604 (feat): trasabilitate în Langfuse. AC: fiecare rulare are trace cu unelte apelate și timp.
- FP-605 (eval): set de 50 de cazuri etichetate din ground truth, cu metrici: Top-1, Top-2, halucinații de dovadă. AC: raport în `reports/agent_eval.md`.
- FP-606 (docs): ADR-024 despre limitele agentului, cu rezultatele reale. AC: nicio afirmație care nu e susținută de eval.

### Sprint 7: Livrare și pachet pentru interviu (săpt. 13-14)
**Obiectiv:** sistemul rulează complet, e documentat și poate fi prezentat.

- FP-701 (chore): Docker Compose complet, cu toate serviciile. AC: pornire de la zero într-o comandă.
- FP-702 (ci): CD în GitHub Actions (build și publicare imagini). AC: release taguit automat.
- FP-709 (spike, ADR-019, max. 4 ore, înainte de FP-703): extensia TimescaleDB pe PostgreSQL Flexible, mesaj de test EMQX → Event Grid MQTT cu certificat, cost lunar estimat. AC: rezultatele scrise în ADR-019 sau într-un ADR nou.
- FP-703 (feat, obligatoriu din ADR-017): Terraform pentru resursele Azure din ADR-019 (Container Apps, Event Grid, PostgreSQL Flexible, ADLS Gen2, Key Vault, Log Analytics, buget), cu starea în backend `azurerm`. AC: `terraform plan` fără erori.
- FP-707 (feat, ADR-017): deploy complet pe Azure, din Terraform. AC: `terraform apply` creează resursele, `terraform destroy` le șterge fără rămășițe.
- FP-708 (learning, ADR-017): certificarea DP-900. AC: certificat în dosarul proiectului până la finalul Sprintului 7.
- FP-704 (test): test end-to-end: simulator → alertă → API. AC: rulează în CI, nightly.
- FP-705 (docs): README final, diagrame, ghid de rulare, limitări, ce ai face mai departe.
- FP-706 (docs): pachet pentru interviu: 1 pagină de decizii cheie, metrici, demo video, retrospectivă.

## 6. Definition of Done (DoD)

Un ticket e gata când:
- codul e în `main` prin PR, cu revizuire;
- testele trec, CI e verde;
- criteriile de acceptare sunt verificate (nu doar presupuse);
- documentația e actualizată dacă s-a schimbat comportamentul;
- există o intrare în journal cu ce s-a învățat.

## 7. Ceremonii (cum arată un sprint)

- **Planificare (ziua 1):** alegi ticketele, scrii obiectivul sprintului, estimezi.
- **Zilnic (5 minute, în journal):** ce ai făcut, ce blochează, ce urmează.
- **Demo (ultima zi):** arăți ce funcționează, cu date reale din sistem.
- **Retrospectivă:** 3 lucruri care au mers, 3 care nu, 1 schimbare pentru sprintul următor. Se scrie în `docs/retro/`.

## 8. Riscuri

| Risc | Probabilitate | Impact | Plan |
|---|---|---|---|
| Sparkplug B sau OPC UA mai complicat decât s-a estimat | Mare | Mediu | ADR-003 deja amână Sparkplug; OPC UA are fallback pe date direct în MQTT |
| Dataset-uri publice fără text în ordinele de lucru | Mare | Mare | Generăm ordine de lucru sintetice realiste, documentate ca atare |
| Agentul halucinează sau are performanță slabă | Mare | Mediu | Eval obligatoriu (FP-605), cu raportare onestă; rezultatul slab e și el material pentru interviu |
| Timp insuficient (săptămâni cu program aglomerat) | Mare | Mare | Prioritizare: sprinturile 1-4 sunt obligatorii, 5-7 se pot reduce |
| Costuri cloud | Mic | Mediu | Dezvoltare locală; Azure doar la FP-703 și oprit imediat; buget cu alertă (ADR-019) |
| Scope prea mare pentru 25 h/sprint (Spark, Azure, DP-900, ML, agent) | Mare | Mare | Ordinea de tăiere, dacă rămâi în urmă: întâi Sprint 6 (agentul se reduce la o singură unealtă și eval pe 20 de cazuri), apoi FP-702 (CD). Azure și Spark rămân, fiindcă le cer anunțurile din Brașov și Timișoara |
| Telemetria și eticheta de adevăr pe ceasuri diferite | Rezolvat | Mare | ADR-021: `SourceTimestamp` și `start_ts`/`end_ts` absolute, testate |

## 9. Ce trebuie să poți spune la interviu

Pentru fiecare sprint: problema, decizia, alternativa respinsă, rezultatul măsurat, ce ai face diferit.

Ordinea de povestire: problema (calitatea datelor în mentenanță) → arhitectura → decizia cea mai grea (de exemplu ADR-007 sau ADR-012) → rezultatele reale din eval → limitările.

Recruiterii și inginerii de date întreabă de obicei: „de ce ai ales asta?”, „ce s-ar strica la 10 ori mai mult volum?”, „cum ai testat?”, „ce ai fi făcut diferit?”. Răspunsurile sunt în ADR-uri și în journal.

## 10. Starea pregătirii

Înainte de Sprintul 1:
- [x] ADR-001 până la ADR-018 scrise și acceptate
- [x] Docker, Python 3.12 și cont GitHub verificate
- [x] Primul journal creat (scris la finalul Sprintului 1; de acum, zilnic)
- [x] Board cu ticketele Sprintului 1 (Azure Boards)

Înainte de Sprintul 2:
- [x] Retrospectiva Sprintului 1 în `docs/retro/` (șablon: `docs/retro/TEMPLATE.md`)
- [ ] ADR-019…022 citite și înțelese
- [x] Work items FP-201…209 în Azure Boards, inclusiv cele noi (FP-208, FP-209)
