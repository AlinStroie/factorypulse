# ADR-017: Azure, Spark și DP-900 devin obligatorii

- **Status:** Accepted
- **Data:** 2026-10-18
- **Înlocuiește:** nimic. Completează ADR-007 (Pandas în v1) și ADR-016 (Terraform opțional).

## Context

Anunțurile reale din piață (Schaeffler Data Engineer, Timișoara DevOps și cloud) cer Azure (Data Factory, Data Lake, IoT Hub, Databricks), Spark și cloud real. Stack-ul v1 avea Azure doar ca extensie opțională și Spark doar ca cale documentată. Asta lăsa proiectul bun pe Python și ML, dar nu pe stack-ul pe care îl cer angajatorii.

## Decizie

1. **Deploy pe Azure** devine obligatoriu: Azure Container Apps pentru API și ingestor, ADLS Gen2 pentru stratul bronze/silver/gold. Resursele sunt definite în Terraform (FP-707), nu create manual.
2. **Un job Spark** devine obligatoriu: bronze → silver în PySpark (FP-207). Rulează local, cu aceleași rezultate ca varianta Pandas. Databricks se folosește dacă e disponibil, altfel Spark local.
3. **Certificarea Azure DP-900** devine țintă obligatorie până la finalul Sprintului 7 (FP-708).

Pandas rămâne pentru calitate și evaluare în v1. Spark se folosește doar pentru transformarea mare bronze → silver.

## Alternative respinse

- **Doar local, fără cloud:** nu acoperă cerințele anunțurilor și nu arată IaC în practică.
- **Doar Spark, fără Pandas:** complexitate inutilă pentru volumul de date al proiectului; Pandas rămâne mai ușor de depanat.
- **AWS în loc de Azure:** Schaeffler și firmele din Timișoara folosesc Azure, deci dovada trebuie să fie Azure.

## Consecințe

- Costuri Azure. Mitigare: buget lunar cu alertă și oprirea resurselor după fiecare sesiune de test.
- Timp suplimentar, estimat la ~20-25 de ore, distribuit în Sprinturile 2 și 7.
- Proiectul devine mai aproape de un job real. Trebuie să poți explica de ce Azure, de ce Spark și ce ai schimba dacă volumul crește.

## Verificare

- FP-207: același set de date produce aceleași rezultate în Pandas și în Spark.
- FP-707: `terraform apply` creează resursele, `terraform destroy` le șterge, fără resurse rămase.
- FP-708: certificat DP-900 în dosarul proiectului.
