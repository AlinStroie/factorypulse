# ADR-025: Bronze în Parquet: conținut, partiționare și fișiere mici

- **Status:** Accepted
- **Data:** 2026-10-22
- **Completează:** ADR-006 (Parquet bronze/silver/gold) și ADR-020 (bronze e sursa de adevăr).
- **Notă:** ADR-023 și ADR-024 sunt rezervate în plan pentru Sprintul 6.

## Context

ADR-020 cere ca ingestorul să scrie bronze înaintea TimescaleDB, iar ack-ul către broker vine abia după scriere (FP-201). Fiecare lot (500 de mesaje sau 1 s) trebuie deci să fie pe disc înainte de ack. Un fișier Parquet devine însă citibil abia după ce e închis, pentru că metadatele se scriu la final. Un fișier per lot înseamnă ~86 400 de fișiere pe zi: listare lentă, citire lentă, overhead mare în Spark (FP-207).

## Decizie

1. **Conținut:** `ingestion_ts` (UTC), `topic`, `payload` (octeții exact cum au venit). Bronze nu interpretează payload-ul; mesajele invalide ajung și ele aici. Parsarea e în silver (FP-205).
2. **Partiționare Hive după ziua sosirii:** `bronze/telemetry/dt=AAAA-LL-ZZ/`. Un mesaj stricat poate să n-aibă `ts`, dar are mereu momentul sosirii. Partiționarea după timpul evenimentului se face în silver.
3. **Un fișier per lot, plus compactare orară.** Fișierul se scrie ca temporar (nume cu punct, ignorat de cititori), cu `fsync`, apoi se redenumește atomic. La un minut după terminarea unei ore, ingestorul unește fișierele acelei ore în `hour-HH.parquet` și le șterge pe cele mici. Fișierele întârziate se adaugă la fișierul compactat existent.
4. **Compresie zstd.**

## Alternative respinse

- **JSON Lines pentru aterizare, conversie orară în Parquet:** append simplu, dar două formate și două coduri de citire.
- **Loturi rare (1 minut):** puține fișiere, dar latența până în TimescaleDB crește la un minut, contrar alertelor din ADR-022.
- **Fișier Parquet ținut deschis, cu row groups adăugate:** fișierul nu e citibil până la închidere, iar o cădere îl pierde după ce mesajele au fost confirmate.

## Consecințe

- Pentru ora curentă există până la ~3600 de fișiere mici; după compactare, unul pe oră (24 pe zi).
- Între scrierea fișierului compactat și ștergerea celor mici, un cititor poate vedea rânduri de două ori. Silver deduplică (FP-205).
- Compactarea rulează în bucla ingestorului, deci ingestia stă câteva secunde o dată pe oră. Brokerul ține mesajele cât timp ingestorul nu confirmă.
- Retenția de 7 zile pe disc local (ADR-020) rămâne de implementat într-un tichet separat.

## Verificare

- `tests/test_bronze.py`: citire cu pandas (AC FP-203), octeți păstrați exact, partiții la miezul nopții, compactare doar pentru orele terminate, fișiere întârziate.
- `tests/test_ingestor.py`: bronze primește tot lotul înaintea bazei de date; dacă bronze eșuează, nu se scrie nimic în DB și nu se trimite ack; la reîncercare, bronze nu se dublează.
