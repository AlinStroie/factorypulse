# Retrospectivă Sprint 1 (2026-10-19)

> Scrisă la finalul sprintului, din istoricul git, PR-uri, Azure Boards și notițele din ghidul personal. Am lucrat cu Claude Code ca asistent (Haiku în prima zi, Opus la revizuire). Deciziile și verificările le-am făcut eu, iar documentul spune deschis cum am folosit asistentul.

## Obiectivul sprintului

„Repo funcțional, CI verde, simulatorul publică date prin MQTT.”

**Atins.** Simulatorul OPC UA (3 mașini, 13 senzori, defecte injectate) publică prin bridge în EMQX, iar CI-ul rulează pe fiecare PR. La revizuirea de la final am găsit o problemă care ar fi blocat Sprintul 4 și am rezolvat-o tot în acest sprint (detalii mai jos).

## Cifre

| Ce | Valoare |
|---|---|
| Story points planificate / finalizate | 21 / 32 (11 SP din revizuirea de la final, neplanificați) |
| Work items închise | 12 din 12 |
| PR-uri | 15 (#1–#15), toate cu CI verde |
| Teste / coverage | 23 de teste, 89% pe `src/` (prag de 80% impus în CI din acest sprint) |
| Defecte găsite | 1 major (eticheta de adevăr pe alt ceas decât telemetria), găsit la revizuire, nu în producție |
| Ore estimate / reale | 25 h capacitate / [completează: orele reale] |

## Cum am lucrat

1. **Întâi piața, apoi planul.** Înainte de cod am căutat anunțuri reale pentru Brașov și Timișoara (eJobs, LinkedIn, site-ul de cariere Schaeffler) și le-am notat în `piata_brasov_it.md`. Hipo era în mentenanță, iar eJobs a cerut verificare Cloudflare pe unele căutări. Am notat asta, ca să nu trag concluzii din date incomplete. Concluzia: Azure, Spark și cloud apar mult mai des decât ML pur, iar rolurile sunt majoritar mid/senior. De aici a ieșit ADR-017 (Azure, Spark și DP-900 devin obligatorii).
2. **Decizii scrise înainte de cod.** ADR-001…018, fiecare cu alternativa respinsă și motivul. Așa pot răspunde la interviu la „de ce ai ales asta?” fără să improvizez.
3. **Proces ca într-o echipă:** ticket în Azure Boards, branch per ticket, PR cu `AB#`, CI, squash merge, Conventional Commits.
4. **Revizuire la final cu alt model.** Am cerut o analiză critică a codului și a arhitecturii, nu doar o confirmare că e bine. Au ieșit goluri reale, nu cosmetice.

## 3 lucruri care au mers

1. **Planul și ADR-urile înainte de cod.** Când revizuirea a găsit goluri, a fost clar unde se scrie corecția: ADR nou (019–022), nu editare în tăcere a planului.
2. **CI devreme.** Din FP-107, fiecare schimbare trece prin ruff, mypy strict și pytest. La revizuire, refactorizarea bridge-ului s-a făcut fără frică, fiindcă testele prindeau regresiile.
3. **Problemele au fost tratate la cauză, nu ascunse.** Exemple:
   - `egg-info` comis din greșeală: regulă în `.gitignore` și commit nou, fără amend, ca istoricul să rămână clar.
   - Proiectul Azure creat cu procesul Basic: l-am recreat cu Agile, fiindcă procesul nu se schimbă după creare.
   - Testele de integrare picau doar cu coverage: am măsurat întâi (`Server.init()` dura ~30 s cu `settrace`, față de ~1 s fără), apoi am trecut pe `core = "sysmon"`. Nu am mărit pur și simplu timeout-ul.

## 3 lucruri care nu au mers

1. **Revizuirea PR-urilor a fost prea rapidă.** În prima zi, PR-urile au fost mergeate la 2–5 minute după deschidere. Checklistul din WORKFLOW exista, dar nu l-am parcurs cu adevărat. Dovada: eticheta de adevăr avea doar secunde relative, iar telemetria avea ora absolută. Precision/recall din Sprintul 4 nu s-ar fi putut calcula. Problema a trecut prin FP-105 și FP-106 fără să fie observată.
2. **PR-urile înlănțuite (#11–#14) au ajuns în branch-urile intermediare, nu în `main`.** Fiecare PR avea ca bază branch-ul celui dinainte, iar la merge codul a intrat acolo. Am observat-o abia când am verificat ce e în `main`. Am rezolvat cu PR #15 (rebase merge, conținut identic, verificat cu `git diff` gol).
3. **Disciplina de proces a scăpat pe alocuri:**
   - journal-ul zilnic nu l-am ținut, deși DoD-ul îl cere (cel din `docs/journal/` e reconstituit după aceea);
   - AB#7 a rămas Active după merge;
   - căsuța „CI verde” din PR-uri n-a fost bifată după ce CI-ul a trecut;
   - capacitatea din plan (35 h) era nerealistă; cea reală e 25 h;
   - datele sprinturilor din Boards nu se potriveau cu realitatea (Sprint 1 începea pe 26 oct; l-am mutat pe 19 oct).

## Ce am învățat

- **Timpul evenimentului vs. timpul procesării.** Dacă ceasurile nu se potrivesc, evaluarea detecției minte, chiar dacă tot codul „merge”.
- **QoS 1 nu ajunge singur.** Fără `client_id` fix și `clean_session=False`, mesajele neconfirmate se pierd la reconectare.
- **Cod care „merge” nu e același lucru cu cod corect pentru ce urmează.** Revizuirea trebuie să întrebe „ce are nevoie următorul sprint de la asta?”.
- **PR-urile înlănțuite** se mergeau de jos în sus, iar după fiecare merge următorul PR se reorientează pe `main`.
- [completează: ce ai învățat tu, cu cuvintele tale]

## 1 acțiune pentru Sprintul 2

**Niciun PR nu se mergează în aceeași sesiune în care a fost deschis.** Îl recitesc a doua zi, cu checklistul din WORKFLOW §6 parcurs punct cu punct, plus o întrebare nouă în checklist: „ce are nevoie următorul sprint de la acest cod?”. Verificare la retrospectiva Sprintului 2: timpul dintre deschiderea PR-ului și merge, din GitHub.

Acțiuni mai mici, fără work item separat:
- o intrare de journal în aceeași zi cu fiecare PR;
- starea din Boards actualizată imediat după merge;
- Sprint 2 are 29 SP estimați la ~21 SP de capacitate: la planificare tai sau mut ce nu încape, nu sper că încape.
