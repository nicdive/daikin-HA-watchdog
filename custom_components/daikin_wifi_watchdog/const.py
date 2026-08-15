"""Constants for Daikin WiFi Watchdog."""

from __future__ import annotations

DOMAIN = "daikin_wifi_watchdog"
DAIKIN_DOMAIN = "daikin"

CONF_CHECK_INTERVAL = "check_interval"
CONF_FAILURES_BEFORE_REBOOT = "failures_before_reboot"
CONF_AUTO_REBOOT = "auto_reboot"
CONF_REBOOT_COOLDOWN = "reboot_cooldown"
CONF_MAX_SOFT_REBOOTS_PER_DAY = "max_soft_reboots_per_day"
CONF_HARD_REBOOT_SWITCHES = "hard_reboot_switches"
CONF_HTTP_TIMEOUT = "http_timeout"
CONF_WATCHDOG_ENABLED = "watchdog_enabled"
CONF_NOTIFICATIONS_ENABLED = "notifications_enabled"
CONF_NOTIFY_SERVICE = "notify_service"

DEFAULT_CHECK_INTERVAL = 60
DEFAULT_FAILURES_BEFORE_REBOOT = 3
DEFAULT_AUTO_REBOOT = True
DEFAULT_REBOOT_COOLDOWN = 120
DEFAULT_MAX_SOFT_REBOOTS_PER_DAY = 6
DEFAULT_HTTP_TIMEOUT = 8
DEFAULT_WATCHDOG_ENABLED = True
DEFAULT_NOTIFICATIONS_ENABLED = True

ERROR_CODES_UNHEALTHY = {255}

ATTR_HOST = "host"
ATTR_MAC = "mac"
ATTR_DAIKIN_ENTRY_ID = "daikin_entry_id"
ATTR_ERROR_CODE = "error_code"
ATTR_DETAIL = "detail"
ATTR_SOFT_REBOOTS_TODAY = "soft_reboots_today"
ATTR_LAST_REBOOT = "last_reboot"

SERVICE_REBOOT = "reboot"
SERVICE_CHECK_NOW = "check_now"

PLATFORMS = ["binary_sensor", "button", "sensor", "switch"]
