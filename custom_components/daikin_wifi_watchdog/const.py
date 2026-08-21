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

STORAGE_KEY = f"{DOMAIN}_runtime"
STORAGE_VERSION = 1

# Official Daikin integration keys.
KEY_MAC = "mac"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
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
