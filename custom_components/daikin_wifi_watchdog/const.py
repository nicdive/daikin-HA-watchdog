"""Constants for Daikin WiFi Watchdog."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "daikin_wifi_watchdog"
DAIKIN_DOMAIN = "daikin"

CONF_CHECK_INTERVAL = "check_interval"
CONF_FAILURES_BEFORE_REBOOT = "failures_before_reboot"
CONF_AUTO_REBOOT = "auto_reboot"
CONF_REBOOT_COOLDOWN = "reboot_cooldown"
CONF_MAX_SOFT_REBOOTS_PER_DAY = "max_soft_reboots_per_day"
CONF_HARD_REBOOT_SWITCHES = "hard_reboot_switches"
CONF_HARD_REBOOT_OFF_SECONDS = "hard_reboot_off_seconds"
CONF_HTTP_TIMEOUT = "http_timeout"
CONF_WATCHDOG_ENABLED = "watchdog_enabled"
CONF_NOTIFICATIONS_ENABLED = "notifications_enabled"
CONF_NOTIFY_SERVICE = "notify_service"
CONF_RELOAD_DAIKIN = "reload_daikin"
CONF_CONFIGURE_HARD_SWITCHES = "configure_hard_switches"
CONF_HARD_REBOOT_SWITCH = "hard_reboot_switch"

# Climate / heating management
CONF_CLIMATE_ENABLED = "climate_enabled"
CONF_CONFIGURE_CLIMATE = "configure_climate"
CONF_CONFIGURE_HEAT_PRESETS = "configure_heat_presets"
CONF_CONFIGURE_COOL_PRESETS = "configure_cool_presets"
CONF_SALON_TEMP_SENSOR = "salon_temp_sensor"
CONF_OUTDOOR_TEMP_SENSOR = "outdoor_temp_sensor"
CONF_PRESENCE_SENSOR = "presence_sensor"
CONF_SUN_ENTITY = "sun_entity"
CONF_NIGHT_START_HOUR = "night_start_hour"
CONF_NIGHT_END_HOUR = "night_end_hour"
CONF_OPENING_SENSORS = "opening_sensors"
CONF_OPENING_DELAY_SECONDS = "opening_delay_seconds"
CONF_HEAT_PRESETS = "heat_presets"
CONF_COOL_PRESETS = "cool_presets"
CONF_HEAT_ON_SALON_BELOW = "heat_on_salon_below"
CONF_HEAT_ON_OUTDOOR_BELOW = "heat_on_outdoor_below"
CONF_HEAT_OFF_SALON_ABOVE = "heat_off_salon_above"
CONF_HEAT_OFF_OUTDOOR_ABOVE = "heat_off_outdoor_above"
CONF_COOL_ON_SALON_ABOVE = "cool_on_salon_above"
CONF_COOL_ON_OUTDOOR_ABOVE = "cool_on_outdoor_above"
CONF_COOL_OFF_OUTDOOR_BELOW = "cool_off_outdoor_below"
CONF_HEAT_MODE = "heat_mode"
CONF_COOL_MODE = "cool_mode"
CONF_AUTO_HEAT = "auto_heat"
CONF_AUTO_COOL = "auto_cool"

DEFAULT_CHECK_INTERVAL = 60
DEFAULT_FAILURES_BEFORE_REBOOT = 3
DEFAULT_AUTO_REBOOT = True
DEFAULT_REBOOT_COOLDOWN = 120
DEFAULT_MAX_SOFT_REBOOTS_PER_DAY = 6
DEFAULT_HTTP_TIMEOUT = 8
DEFAULT_WATCHDOG_ENABLED = True
DEFAULT_NOTIFICATIONS_ENABLED = True
DEFAULT_HARD_REBOOT_OFF_SECONDS = 15
DEFAULT_RELOAD_DAIKIN = True
DEFAULT_CLIMATE_ENABLED = True
DEFAULT_HEAT_MODE = "off"
DEFAULT_COOL_MODE = "off"
DEFAULT_AUTO_HEAT = False
DEFAULT_AUTO_COOL = False
DEFAULT_SUN_ENTITY = "sun.sun"
DEFAULT_NIGHT_START_HOUR = 21
DEFAULT_NIGHT_END_HOUR = 6

ERROR_CODES_UNHEALTHY = {255}

ATTR_HOST = "host"
ATTR_MAC = "mac"
ATTR_DAIKIN_ENTRY_ID = "daikin_entry_id"
ATTR_ERROR_CODE = "error_code"
ATTR_DETAIL = "detail"
ATTR_SOFT_REBOOTS_TODAY = "soft_reboots_today"
ATTR_LAST_REBOOT = "last_reboot"

SERVICE_REBOOT = "reboot"
SERVICE_HARD_REBOOT = "hard_reboot"
SERVICE_CHECK_NOW = "check_now"
SERVICE_APPLY_HEAT_MODE = "apply_heat_mode"
SERVICE_APPLY_COOL_MODE = "apply_cool_mode"
SERVICE_CLIMATE_EVALUATE = "climate_evaluate"

STORAGE_KEY = f"{DOMAIN}_runtime"
STORAGE_VERSION = 1
CLIMATE_STORAGE_KEY = f"{DOMAIN}_climate"
CLIMATE_STORAGE_VERSION = 1

SIGNAL_CLIMATE_UPDATED = f"{DOMAIN}_climate_updated"

# Official Daikin integration keys.
KEY_MAC = "mac"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

STATUS_OPTIONS = [
    "ok",
    "error_code",
    "unreachable",
    "bad_response",
    "disabled",
    "rebooting",
]
