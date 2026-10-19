# Retrospectivă Sprint 1 (2026-10-19)

## Obiectivul sprintului

„Repo funcțional, CI verde, simulatorul publică date prin MQTT.”

**Atins.** Simulatorul OPC UA (3 mașini, 13 senzori, defecte injectate) publică prin bridge în EMQX, iar CI-ul rulează pe fiecare PR. La revizuirea de la finalul sprintului am adăugat cinci tichete care pregătesc Sprinturile 2–4: eticheta de adevăr pe ceas absolut, bridge robust, coverage impus în CI, imagini Docker și ADR-urile 019–022.

## Cifre

| Ce | Valoare |
|---|---|
| Story points finalizate | 32 (21 planificate + 11 adăugate la revizuire) |
| Work items închise | 12 din 12 |
| PR-uri | 15, toate cu CI verde |
| Teste / coverage | 23 de teste, 89% pe `src/` (prag de 80% impus în CI) |
| Defecte | 1 major, găsit și rezolvat în sprint (eticheta de adevăr pe alt ceas decât telemetria) |

## Abordare

1. **Piața înaintea planului.** Am analizat anunțuri reale din Brașov și Timișoara (eJobs, LinkedIn, Schaeffler) și le-am notat cu sursa. Când o sursă nu era disponibilă (Hipo în mentenanță, verificare Cloudflare pe eJobs), am notat-o, ca să nu trag concluzii din date incomplete. Rezultat: Azure, Spark și cloud apar constant în cerințe, deci au devenit obligatorii în proiect (ADR-017).
2. **Decizii scrise înainte de cod.** ADR-001…018, fiecare cu alternativa respinsă și motivul.
3. **Flux de echipă:** ticket în Azure Boards, branch per ticket, PR legat cu `AB#`, CI, squash merge, Conventional Commits.
4. **Revizuire la final de sprint, cu întrebarea „ce are nevoie următorul sprint de la acest cod?”.** Așa a ieșit la iveală problema de ceas din eticheta de adevăr, care ar fi blocat evaluarea din Sprintul 4.

## Ce a mers bine

1. **ADR-urile au făcut schimbările ușor de urmărit.** Golurile găsite la revizuire au fost rezolvate prin ADR-uri noi (019–022), nu prin modificarea în tăcere a planului.
2. **CI-ul de la început.** ruff, mypy strict și pytest pe fiecare PR. Refactorizarea bridge-ului s-a făcut sigur, pentru că testele prindeau regresiile.
3. **Probleme rezolvate la cauză.** Exemple:
   - procesul Azure DevOps nu se poate schimba după creare, așa că am recreat proiectul cu Agile;
   - artefactele de build au fost scoase din repo printr-un commit nou și o regulă în `.gitignore`, ca istoricul să rămână clar;
   - testele de integrare picau sub coverage. Am măsurat întâi: `Server.init()` din asyncua dura ~30 s cu `settrace`, față de ~1 s fără. Am trecut pe `core = "sysmon"` (~2 s), în loc să măresc timeout-ul.

## Ce îmbunătățim

1. **Revizuirea PR-urilor să privească și înainte.** Checklistul acoperea corectitudinea codului curent, dar nu și cerințele sprinturilor următoare. Am adăugat în WORKFLOW întrebarea „ce are nevoie următorul sprint de la acest cod?”.
2. **Procedură pentru PR-uri înlănțuite.** La merge, PR-urile #11–#14 au intrat în branch-urile intermediare, nu în `main`. Am adus codul în `main` prin PR #15 (rebase merge, conținut verificat identic). De acum, după fiecare merge, următorul PR se reorientează pe `main`. Pasul e trecut în checklist.
3. **Board-ul la zi în aceeași zi.** Starea work items și criteriile de acceptare din PR se actualizează imediat după merge, iar journal-ul se scrie zilnic.

## Ce am învățat

- **Timpul evenimentului vs. timpul procesării.** Telemetria și eticheta de adevăr trebuie să folosească același ceas, altfel evaluarea detecției nu e corectă.
- **QoS 1 are efect la reconectare** doar cu `client_id` fix și `clean_session=False`.
- **Bronze ca sursă de adevăr.** Un bug în validare se corectează reconstruind silver din bronze (ADR-020).
- **Edge vs. cloud.** Fabrica și brokerul local rămân la edge; datele urcă în cloud printr-un gateway (ADR-019).

## Acțiune pentru Sprintul 2

**Fiecare PR trece prin checklistul complet din WORKFLOW §6, inclusiv punctele noi, înainte de merge.** Verificare la retrospectiva Sprintului 2: toate PR-urile au checklistul bifat, iar `main` conține tot ce s-a mergeat.

La planificarea Sprintului 2: 29 SP estimați. Prioritizez FP-201…205 și FP-208 (fluxul de bază, plus contractul), iar restul intră în funcție de ritm.
