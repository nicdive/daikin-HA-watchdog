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

Aucune saisie d’IP manuelle. Les identifiants locaux (mot de passe / UUID) déjà stockés par Daikin AC sont réutilisés.

Dans les options, tu peux associer une **prise par climatisation** (le formulaire affiche le nom de l’unité) et choisir ton **notify Companion**.

## Entités globales
| Entité | Rôle |
|--------|------|
| `switch.*_watchdog_enabled` | Active / coupe toute la surveillance |
| `switch.*_notifications_enabled` | Active / coupe les notifs plantage & reboot vers le mobile |

## Entités créées (par clim)
| Entité | Rôle |
|--------|------|
| `binary_sensor.*_wifi_healthy` | OK / HS |
| `sensor.*_wifi_status` | `ok` / `error_code` / `unreachable` / `rebooting` / … |
| `sensor.*_wifi_error_code` | ex. `255` |
| `sensor.*_wifi_last_reboot` | timestamp (conservé après redémarrage de HA) |
| `sensor.*_wifi_soft_reboots_today` | compteur journalier (persisté) |
| `sensor.*_wifi_consecutive_failures` | échecs d’affilée avant reboot |
| `button.*_reboot_wifi_module` | reboot logiciel manuel |
| `button.*_hard_reboot_wifi_module` | power-cycle si une prise est configurée |

Un export **Diagnostics** est disponible sur l’entrée d’intégration (utile pour un ticket).

## Comportement
1. Poll parallèle `http(s)://IP/common/basic_info` (IP + auth lues depuis Daikin AC)
2. Un timeout unique est retenté 1 s plus tard pour éviter les faux positifs
3. Si `err=255` ou injoignable → compteur d’échecs
4. Après N échecs → soft reboot `GET /common/reboot` (les timeouts/coupures TCP pendant le reboot sont considérés comme un succès)
5. Recharge ensuite l’entrée Daikin AC pour reconnecter l’intégration
6. Optionnel : prise `switch.*` en secours (power-cycle, durée réglable)
7. Quota journalier, cooldown, et issues HA si le module reste injoignable sans prise

## Services
```yaml
service: daikin_wifi_watchdog.check_now

service: daikin_wifi_watchdog.reboot
data:
  host: 192.168.1.50

service: daikin_wifi_watchdog.hard_reboot
data:
  host: 192.168.1.50
```

## Options utiles
- Intervalle de contrôle
- Nombre d’échecs avant reboot
- Auto-reboot on/off
- Cooldown / quota journalier
- Durée d’extinction de la prise
- Rechargement Daikin AC après reboot
- Switch de hard-reboot **par** module Daikin (étape dédiée avec le nom de la clim)

## Prérequis
- Modules avec **API locale** (BRP069A/B, Emura classiques, BRP072C avec UUID)
- Intégration officielle **Daikin AC** déjà configurée

Les modules cloud-only (certains BRP069C) ne répondent souvent plus à `/common/reboot` : configure alors une prise dans les options.
