# ADR-019: Topologia pe Azure (edge local, cloud pentru ingestie, stocare și API)

- **Status:** Accepted
- **Data:** 2026-10-19
- **Completează:** ADR-017 (Azure obligatoriu), care spune *ce* servicii, dar nu *unde* rulează fiecare componentă.

## Context

ADR-017 cere Container Apps și ADLS Gen2, dar lasă deschise patru întrebări: unde stă brokerul MQTT, unde stă baza de date, cum ajung datele din „fabrică” în cloud și cum se gestionează secretele. Fără răspuns, Sprintul 7 (FP-703, FP-707) nu poate fi estimat.

Într-o fabrică reală, PLC-urile și serverul OPC UA nu sunt în cloud. Ele rămân în rețeaua fabricii (edge), iar datele urcă în cloud printr-un gateway.

## Decizie

**Edge (local, Docker Compose):** simulator OPC UA, bridge, EMQX. Rolul lor e cel al fabricii. Nu se mută în cloud.

**Edge → cloud:** EMQX trimite mai departe topicurile `factory/#` (MQTT bridge, funcție nativă EMQX) spre **Azure Event Grid, broker MQTT** (namespace Event Grid). Autentificare cu certificat client X.509, TLS obligatoriu.

**Cloud (Terraform, un resource group per mediu):**

| Componentă | Serviciu Azure | Notă |
|---|---|---|
| Ingestor | Container Apps | abonat la Event Grid MQTT |
| API (FastAPI) | Container Apps | ingress HTTPS |
| Telemetrie, alerte, ordine de lucru | Azure Database for PostgreSQL Flexible Server (Burstable) | TimescaleDB, dacă extensia e permisă (vezi Verificare) |
| Bronze, silver, gold | ADLS Gen2 (Storage Account cu namespace ierarhic) | un container per strat |
| Imagini | GitHub Container Registry (ghcr.io) | gratuit pentru repo public; fără ACR |
| Secrete | Key Vault | Container Apps citesc secretele prin managed identity |
| Loguri | Log Analytics workspace | cerut oricum de mediul Container Apps |
| Cost | Budget pe resource group, cu alertă pe e-mail | |

**Identitate:** Container Apps folosesc managed identity. Accesul la ADLS se dă prin rol RBAC (Storage Blob Data Contributor). În cod nu există chei de storage.

**Stare Terraform:** backend `azurerm` într-un storage account separat, creat o singură dată de un script de bootstrap. Starea nu se ține local și nu intră în git.

## Alternative respinse

- **EMQX pe Container Apps:** brokerul ar avea nevoie de ingress TCP (MQTT nu e HTTP). E posibil, dar adaugă rețea și configurare care nu ajută la obiectiv. În plus, o fabrică nu își mută brokerul local în cloud.
- **Azure IoT Hub:** apare în anunțuri, dar e gândit pentru dispozitive individuale (device twins, provisioning), nu pentru un broker MQTT generic cu topicurile noastre. Conceptele (edge → cloud, autentificare per dispozitiv) se pot explica la interviu prin comparație cu Event Grid.
- **Ingestorul local, scrie direct în cloud:** cel mai ieftin, dar atunci cloud-ul e doar stocare, iar partea de cloud din proiect devine neconvingătoare.
- **Azure Container Registry:** costă lunar, iar ghcr.io e deja legat de GitHub Actions.

## Consecințe

- Cost estimat la rulări scurte și oprire după fiecare test: câțiva dolari pe lună. Cea mai scumpă componentă e PostgreSQL Flexible Server, care se oprește (`az postgres flexible-server stop`) între sesiuni. Cifra se verifică în Azure Pricing Calculator înainte de FP-707.
- Se adaugă un ticket de spike, FP-709 (vezi Verificare), înainte de FP-703.
- Ingestorul trebuie să poată citi din două brokere (EMQX local, Event Grid în cloud). Adresa, portul, TLS-ul și certificatul vin din variabile de mediu, la fel ca la bridge.
- **Fallback documentat:** dacă Event Grid MQTT consumă prea mult timp, ingestorul rulează local, iar cloud-ul păstrează ADLS, PostgreSQL și API-ul. Schimbarea se face printr-un ADR nou, nu în tăcere.

## Verificare

Spike FP-709, maximum 4 ore, înainte de FP-703:
1. Extensia TimescaleDB e în lista de extensii permise pe PostgreSQL Flexible Server, pe versiunea aleasă? Dacă nu: PostgreSQL simplu, cu partiționare nativă pe timp, plus un ADR nou care înlocuiește partea relevantă din ADR-005.
2. EMQX local publică un mesaj de test în Event Grid MQTT, cu certificat.
3. Costul estimat pe lună, cu resursele oprite între sesiuni.
