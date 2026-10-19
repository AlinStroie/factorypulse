# Workflow FactoryPulse

Document de proces. Descrie cum lucrăm și de ce. Se actualizează prin ADR, ca PLAN_PROIECT.md.

## 1. Roluri (simulate)

- **Product Owner:** scrie și prioritizează work items, definește ce înseamnă „gata”.
- **Developer:** construiește, testează, deschide PR-uri, documentează.
- **Reviewer:** revizuiește PR-urile, folosind checklistul din secțiunea 6. Dacă un prieten din domeniu acceptă, îl folosești ca reviewer extern pentru 1-2 PR-uri cheie.
- **Scrum Master:** tu, prin ceremonii și retrospective. Ține sprinturile în timp.

Tu le joci pe toate, dar le păstrezi separate: un PR nu se aprobă de același „gând” care l-a scris, fără checklist.

## 2. Tipuri de work items (Azure DevOps, process Agile)

- **Epic:** o zonă mare (ex. „Ingestie”, „Detecție anomalii”, „Agent RCA”).
- **User Story:** o funcționalitate văzută din perspectiva utilizatorului (ex. „Ca inginer de mentenanță, vreau să primesc alertă când vibrația depășește pragul”).
- **Task:** pas tehnic dintr-un story, cu estimare în ore.
- **Bug:** defect găsit, cu severitate (1 critic, 2 major, 3 minor, 4 cosmetic).
- **Spike:** investigație cu timp limitat (ex. test de modele LLM). Rezultatul e un ADR.

## 3. Stări

`New` → `Active` → `Resolved` → `Closed`

- `New`: în backlog, nu e pregătit.
- `Active`: lucrezi la el.
- `Resolved`: PR deschis și CI verde.
- `Closed`: PR merged și criteriile de acceptare verificate.

## 4. Definition of Ready (înainte să intre în sprint)

- criterii de acceptare clare;
- estimare făcută (story points);
- dependențele sunt cunoscute;
- nu depinde de un ADR nerezolvat.

## 5. Definition of Done

- PR merged în `main`, legat de work item;
- CI verde: lint, teste, build;
- criteriile de acceptare verificate, nu presupuse;
- documentație actualizată dacă s-a schimbat comportamentul;
- intrare în journal cu ce ai învățat.

## 6. Checklist pentru PR (self-review)

- [ ] Titlul și descrierea spun ce se schimbă și de ce.
- [ ] Work item legat (`AB#123` în descriere).
- [ ] Testele acoperă cazul nou și cazurile de eroare.
- [ ] Niciun secret în cod. Configurarea vine din variabile de mediu.
- [ ] Commit-uri Conventional (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- [ ] Nu am lăsat cod comentat sau TODO fără work item.
- [ ] Documentația și ADR-urile sunt la zi.

## 7. Git

- Branch principal: `main`, protejat. Nu se face push direct.
- Branch-uri: `feature/AB123-scurt-descriere` sau `fix/AB123-...`.
- Merge: squash, ca istoricul din `main` să fie curat.
- Release: tag semantic (`v0.1.0` la MVP, `v1.0.0` la final), cu CHANGELOG.

## 8. Ceremonii (2 săptămâni)

- **Refinement (1 oră, săptămâna 1, miercuri):** pregătești următorul sprint: stories, estimări, criterii.
- **Planificare (ziua 1, ~1 oră):** alegi work items pentru sprint, în limita capacității (25 de ore: 2,5 ore pe zi × 10 zile).
- **Daily (async, în journal, 5 minute):** ce ai făcut ieri, ce faci azi, ce te blochează.
- **Review (ultima zi, ~45 minute):** demo cu date reale din sistem, nu slide-uri.
- **Retrospectivă (ultima zi, ~30 minute):** 3 lucruri care au mers, 3 care nu, 1 acțiune pentru sprintul următor. Fișier în `docs/retro/`.

## 9. Incidente

Simulezi cel puțin un incident pe parcurs: de exemplu, simulatorul se oprește noaptea, sau baza de date se umple. Pentru fiecare:
- work item de tip Bug, cu severitate;
- fișier în `docs/incidents/` cu: ce s-a întâmplat, impact, cauza, cum ai rezolvat, ce previne repetarea;
- ticket de prevenție (ex. alertă de spațiu pe disc).

Un post-mortem bun e unul dintre cele mai puternice lucruri de arătat la interviu.

## 10. Metrici (din Azure Boards Analytics)

- **Velocity:** story points finalizate per sprint.
- **Burndown:** progres în sprint.
- **Cycle time:** de la Active la Closed.
- **Bugs:** număr și severitate, pe sprint.
- **Coverage:** din CI, pe `src/`.

Metricile apar în documentul final, cu tendințele lor, nu doar cu valori finale.

## 11. Documentul final de proces

Se construiește din:
- ADR-urile din `plan_proiect/adr/`;
- journal-ul zilnic, cu tag-urile `#blocker` și `#learn`;
- retrospectivele;
- incidentele;
- metricile din Azure Boards;
- PR-urile legate de work items.

Structura: context, obiectiv, proces și de ce, decizii, dificultăți și cum le-ai rezolvat, rezultate măsurate, ce ai învățat, ce urmează.
