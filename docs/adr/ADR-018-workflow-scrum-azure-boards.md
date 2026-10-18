# ADR-018: Workflow de echipă, Scrum cu Azure DevOps Boards și GitHub

- **Status:** Accepted
- **Data:** 2026-10-18
- **Completează:** ADR-015 (CI pe GitHub Actions), care rămâne valabil.

## Context

Simulăm cât mai aproape de un loc de muncă real într-o firmă industrială care folosește Azure. Planul trebuie să arate ce face o echipă reală: backlog, sprinturi, estimări, PR-uri, revizuire, CI, release și retrospective. Documentul final de proces se scrie din aceste artefacte.

## Decizie

1. **Metodologie:** Scrum, cu sprinturi de 2 săptămâni, planificare, daily async, review și retrospectivă. Kanban pentru fluxul din board.
2. **Tracking:** Azure DevOps Boards (process Agile), organizație gratuită. Îl alegem pentru că Schaeffler și firmele din Timișoara folosesc ecosistemul Microsoft.
3. **Cod:** GitHub, repo public. Recruiterii văd repo-ul, deci e vizibil. Azure Boards se leagă de GitHub: fiecare PR se leagă de un work item.
4. **CI/CD:** GitHub Actions (ADR-015), cu deploy pe Azure (ADR-017).
5. **Jenkins:** nu îl folosim. E relevant de știut, dar stack-ul nostru e GitHub Actions. Dacă un angajator cere Jenkins, îl înveți în câteva zile, fiindcă conceptele sunt aceleași.

## Alternative respinse

- **Doar GitHub Projects:** funcționează, dar nu e ce folosesc firmele mari. Ca simulare de industrie, Azure Boards e mai aproape.
- **Doar Azure DevOps (Repos + Pipelines):** realist, dar repo-ul ar fi mai puțin vizibil pentru recruiteri.
- **Jira:** cea mai răspândită, dar gratuitatea e limitată și nu se leagă la fel de natural cu stack-ul Azure.

## Consecințe

- Trebuie să înveți Azure Boards: work items, backlog, sprint, board, analytics. Două ore de tutorial sunt suficiente la început.
- Fiecare ticket trebuie actualizat în board când se schimbă starea. Asta e disciplina pe care o cer firmele.
- Burndown și velocity vin din Azure Boards Analytics, nu din tabele scrise de mână.

## Verificare

- Fiecare PR are work item legat.
- Board-ul arată starea reală, la zi, la fiecare sprint.
- Există cel puțin un incident simulat, cu post-mortem, documentat în `docs/incidents/`.
