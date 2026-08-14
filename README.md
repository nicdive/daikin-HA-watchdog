# Daikin WiFi Watchdog (Home Assistant)

Custom component Home Assistant qui **récupère automatiquement** les climatisations de l’intégration officielle **Daikin AC** (`daikin`), surveille leurs modules WiFi, et les **reboot** s’ils plantent (`err=255` / timeout) — comme le mode santé du plugin Jeedom.

## Installation

### HACS (recommandé)
1. HACS → Integrations → ⋮ → *Custom repositories*
2. Ajoute l’URL de ce dépôt, catégorie **Integration**
3. Installe **Daikin WiFi Watchdog**
4. Redémarre Home Assistant

### Manuelle
```bash
# copier dans ta config HA
cp -r custom_components/daikin_wifi_watchdog /config/custom_components/
```
Puis redémarre HA.

## Configuration
1. Assure-toi que tes Emura sont déjà ajoutées via **Paramètres → Appareils & services → Daikin AC**
2. Ajoute l’intégration **Daikin WiFi Watchdog**
3. Elle détecte toute seule les IP/MAC des entries `daikin`

Aucune saisie d’IP manuelle.

## Entités créées (par clim)
| Entité | Rôle |
|--------|------|
| `binary_sensor.*_wifi_healthy` | OK / HS |
| `sensor.*_wifi_status` | `ok` / `error_code` / `unreachable` |
| `sensor.*_wifi_error_code` | ex. `255` |
| `sensor.*_wifi_last_reboot` | timestamp |
| `sensor.*_wifi_soft_reboots_today` | compteur journalier |
| `button.*_reboot_wifi_module` | reboot manuel |

## Comportement
1. Poll `http://IP/common/basic_info` (IP lue depuis Daikin AC)
2. Si `err=255` ou injoignable → compteur d’échecs
3. Après N échecs → soft reboot `GET /common/reboot`
4. Recharge ensuite l’entrée Daikin AC pour reconnecter l’intégration
5. Optionnel : prise `switch.*` en secours (power-cycle) dans les options

## Services
```yaml
service: daikin_wifi_watchdog.check_now

service: daikin_wifi_watchdog.reboot
data:
  host: 192.168.1.50
```

## Options utiles
- Intervalle de contrôle
- Nombre d’échecs avant reboot
- Auto-reboot on/off
- Cooldown / quota journalier
- Switch de hard-reboot par module Daikin

## Prérequis
- Modules avec **API locale** (BRP069A/B, Emura classiques)
- Intégration officielle **Daikin AC** déjà configurée

Les modules cloud-only (certains BRP069C) ne répondent souvent plus à `/common/reboot` : configure alors une prise dans les options.
