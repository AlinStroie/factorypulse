# ADR-020: Fluxul datelor: cine scrie bronze, silver și TimescaleDB

- **Status:** Accepted
- **Data:** 2026-10-19
- **Completează:** ADR-005 (TimescaleDB) și ADR-006 (Parquet bronze/silver/gold).

## Context

Planul are atât TimescaleDB, cât și Parquet. Diagrama din PLAN_PROIECT nu spune cine scrie în fiecare și care e sursa de adevăr. Fără regulă clară, apar două copii ale datelor care pot diverge, iar FP-201, FP-203 și FP-205 se calcă pe picioare.

## Decizie

```
MQTT --> [Ingestor] --1--> bronze (Parquet, brut, append-only)
              |
              +--2--> validare contract (ADR-021)
                         | valid                | invalid
                         v                      v
                    TimescaleDB           quarantine (tabel)
                    `telemetry` (hot)

bronze --[job batch, Pandas / PySpark]--> silver (Parquet, curat, tipat, deduplicat)
silver --> antrenare și evaluare ML, rapoarte de calitate, gold
TimescaleDB --> detecție online, alerte, API, Grafana
```

Reguli:
1. **Bronze e sursa de adevăr.** Ingestorul scrie mesajul exact cum a venit, plus `ingestion_ts`. Bronze nu se modifică și nu se șterge.
2. **Ordinea scrierilor:** întâi bronze, apoi TimescaleDB. Dacă scrierea în TimescaleDB eșuează, datele se pot reîncărca din bronze. Cheia unică (mașină, senzor, ts) din FP-202 face reîncărcarea sigură.
3. **TimescaleDB e stocare „caldă”:** ultimele 30 de zile (retention policy), pentru alerte, API și dashboard. Nu e arhivă.
4. **Silver se construiește doar din bronze**, de jobul batch (FP-205 în Pandas, FP-207 în PySpark). Nu se construiește din TimescaleDB.
5. **ML se antrenează și se evaluează pe silver**, ca rezultatele să fie reproductibile. Detecția online citește TimescaleDB.

## Alternative respinse

- **Doar TimescaleDB:** nu avem date brute pentru reprocesare, iar Spark n-ar avea ce citi.
- **Doar Parquet:** alertele în timp real și Grafana ar citi fișiere. Merge, dar e lent și nu seamănă cu un sistem real.
- **Silver din TimescaleDB:** baza devine sursa de adevăr, iar o eroare în validare nu se mai poate corecta retroactiv.

## Consecințe

- Ingestorul are două ieșiri. Fiecare se testează separat, iar testul de integrare verifică că nimic nu se pierde (AC-ul din FP-201).
- Bronze crește continuu. Pe disc local se păstrează 7 zile, apoi se arhivează. Pe ADLS: lifecycle policy spre tier-ul Cool.
- La interviu poți răspunde la „ce faci dacă ai un bug în validare?”: corectezi regula, reconstruiești silver din bronze și reîncarci TimescaleDB.

## Verificare

- Test: un mesaj invalid ajunge în bronze și în `quarantine`, dar nu în `telemetry`.
- Test: dacă TimescaleDB e oprit, bronze primește în continuare mesajele. După repornire, reîncărcarea din bronze nu creează duplicate.
