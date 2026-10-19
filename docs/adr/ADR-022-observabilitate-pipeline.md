# ADR-022: Observabilitatea pipeline-ului

- **Status:** Accepted
- **Data:** 2026-10-19
- **Completează:** ADR-011 (Grafana) și ADR-014 (Langfuse, care acoperă doar agentul).

## Context

Planul monitorizează mașinile (anomalii), dar nu și pipeline-ul. Dacă bridge-ul se oprește noaptea, nimeni nu observă, iar detecția de anomalii tace fără să știm de ce. Anunțurile DevOps și cloud din piață cer explicit monitorizare (CloudWatch, Azure Monitor). Incidentul simulat din WORKFLOW (secțiunea 9) are nevoie de o alertă care să-l prindă.

## Decizie

Trei semnale, puține și utile:

1. **Prospețimea datelor:** pentru fiecare mașină, timpul de la ultimul `ts` primit. Alertă Grafana dacă depășește 60 s.
2. **Latența ingestiei:** `ingestion_ts - ts` (ADR-021), percentila p95. Alertă dacă trece de 10 s timp de 5 minute.
3. **Rata de carantină:** procentul de mesaje invalide pe oră. Alertă dacă trece de 5%.

Implementare locală:
- Ingestorul expune metrici în format Prometheus (`prometheus_client`, endpoint `/metrics`): mesaje primite, mesaje în carantină, latență (histogramă).
- Prometheus în Docker Compose citește metricile ingestorului și pe cele ale EMQX (EMQX expune nativ format Prometheus).
- Prospețimea se calculează în SQL, direct din TimescaleDB (`max(ts)` pe mașină). Nu are nevoie de Prometheus.
- Alertele și dashboard-ul „Pipeline health” sunt în Grafana, versionate ca JSON în `grafana/`.
- Logurile sunt structurate (cheie=valoare), prin `logging` din biblioteca standard.

În Azure: logurile Container Apps ajung în Log Analytics. Alerta de prospețime rămâne în Grafana, pe PostgreSQL. O alertă Azure Monitor pe restarturile containerului ingestorului acoperă cazul în care ingestorul nu mai rulează deloc.

## Alternative respinse

- **OpenTelemetry complet (trace-uri distribuite):** prea mult pentru 3 servicii Python. Rămâne extensie.
- **Doar loguri:** nu poți pune alertă pe „lipsesc date”, iar „lipsesc date” e cel mai des incident real.

## Consecințe

- Un serviciu nou în compose (Prometheus).
- Ticketele FP-209 (metrici în ingestor) și FP-210 (dashboard și alerte pentru pipeline) intră în Sprinturile 2 și 3.
- Incidentul simulat (oprirea bridge-ului) trebuie prins de alerta de prospețime. Asta e testul real pentru acest ADR.

## Verificare

- Cu bridge-ul oprit 2 minute, alerta de prospețime trece în starea Firing. Post-mortem-ul din `docs/incidents/` include captura alertei.
