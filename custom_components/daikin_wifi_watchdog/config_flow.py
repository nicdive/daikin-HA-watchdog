"""Config flow for Daikin WiFi Watchdog."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_CONFIGURE_HARD_SWITCHES,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_OFF_SECONDS,
    CONF_HARD_REBOOT_SWITCH,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_REBOOT_COOLDOWN,
    CONF_RELOAD_DAIKIN,
    CONF_WATCHDOG_ENABLED,
    DAIKIN_DOMAIN,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HARD_REBOOT_OFF_SECONDS,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_REBOOT_COOLDOWN,
    DEFAULT_RELOAD_DAIKIN,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
)


def _guess_mobile_notify(hass: HomeAssistant) -> str:
    """Best-effort match for a Companion notify target."""
    services = hass.services.async_services().get("notify", {})
    mobile: list[str] = []
    preferred: list[str] = []
    for name in services:
        lower = name.lower()
        if not lower.startswith("mobile_app_"):
            continue
        entity = f"notify.{name}"
        mobile.append(entity)
        if "iphone" in lower:
            preferred.append(entity)
    if preferred:
        return preferred[0]
    return mobile[0] if mobile else ""


def _notify_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="notify", multiple=False)
    )


def _switch_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="switch", multiple=False)
    )


class DaikinWifiWatchdogConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-instance config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        daikin_entries = self.hass.config_entries.async_entries(DAIKIN_DOMAIN)
        if user_input is not None:
            notify = user_input.get(CONF_NOTIFY_SERVICE) or _guess_mobile_notify(self.hass)
            return self.async_create_entry(
                title="Daikin WiFi Watchdog",
                data={},
                options={
                    CONF_CHECK_INTERVAL: user_input.get(
                        CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL
                    ),
                    CONF_FAILURES_BEFORE_REBOOT: user_input.get(
                        CONF_FAILURES_BEFORE_REBOOT, DEFAULT_FAILURES_BEFORE_REBOOT
                    ),
                    CONF_AUTO_REBOOT: user_input.get(CONF_AUTO_REBOOT, DEFAULT_AUTO_REBOOT),
                    CONF_REBOOT_COOLDOWN: DEFAULT_REBOOT_COOLDOWN,
                    CONF_MAX_SOFT_REBOOTS_PER_DAY: DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
                    CONF_HTTP_TIMEOUT: DEFAULT_HTTP_TIMEOUT,
                    CONF_HARD_REBOOT_SWITCHES: {},
                    CONF_HARD_REBOOT_OFF_SECONDS: DEFAULT_HARD_REBOOT_OFF_SECONDS,
                    CONF_WATCHDOG_ENABLED: DEFAULT_WATCHDOG_ENABLED,
                    CONF_NOTIFICATIONS_ENABLED: user_input.get(
                        CONF_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED
                    ),
                    CONF_NOTIFY_SERVICE: notify,
                    CONF_RELOAD_DAIKIN: DEFAULT_RELOAD_DAIKIN,
                },
            )

        guessed = _guess_mobile_notify(self.hass)
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_CHECK_INTERVAL, default=DEFAULT_CHECK_INTERVAL
            ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            vol.Required(
                CONF_FAILURES_BEFORE_REBOOT,
                default=DEFAULT_FAILURES_BEFORE_REBOOT,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Required(CONF_AUTO_REBOOT, default=DEFAULT_AUTO_REBOOT): bool,
            vol.Required(
                CONF_NOTIFICATIONS_ENABLED, default=DEFAULT_NOTIFICATIONS_ENABLED
            ): bool,
        }
        if guessed:
            schema[vol.Optional(CONF_NOTIFY_SERVICE, default=guessed)] = _notify_selector()
        else:
            schema[vol.Optional(CONF_NOTIFY_SERVICE)] = _notify_selector()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "daikin_count": str(len(daikin_entries)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return DaikinWifiWatchdogOptionsFlow(config_entry)


class DaikinWifiWatchdogOptionsFlow(config_entries.OptionsFlow):
    """Options flow including notify target and named hard-reboot mapping."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        if config_entry is not None:
            self._config_entry = config_entry
        self._pending: dict[str, Any] = {}
        self._daikin_queue: list[config_entries.ConfigEntry] = []
        self._hard_map: dict[str, str] = {}
        self._index = 0

    def _entry(self) -> config_entries.ConfigEntry:
        return getattr(self, "config_entry", None) or self._config_entry

    def _current_options(self) -> dict[str, Any]:
        return dict(self._entry().options or {})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self._current_options()
        daikin_entries = [
            entry
            for entry in self.hass.config_entries.async_entries(DAIKIN_DOMAIN)
            if entry.source != config_entries.SOURCE_IGNORE
        ]

        if user_input is not None:
            self._pending = {
                CONF_CHECK_INTERVAL: user_input[CONF_CHECK_INTERVAL],
                CONF_FAILURES_BEFORE_REBOOT: user_input[CONF_FAILURES_BEFORE_REBOOT],
                CONF_AUTO_REBOOT: user_input[CONF_AUTO_REBOOT],
                CONF_REBOOT_COOLDOWN: user_input[CONF_REBOOT_COOLDOWN],
                CONF_MAX_SOFT_REBOOTS_PER_DAY: user_input[CONF_MAX_SOFT_REBOOTS_PER_DAY],
                CONF_HTTP_TIMEOUT: user_input[CONF_HTTP_TIMEOUT],
                CONF_HARD_REBOOT_OFF_SECONDS: user_input[CONF_HARD_REBOOT_OFF_SECONDS],
                CONF_RELOAD_DAIKIN: user_input[CONF_RELOAD_DAIKIN],
                CONF_WATCHDOG_ENABLED: current.get(
                    CONF_WATCHDOG_ENABLED, DEFAULT_WATCHDOG_ENABLED
                ),
                CONF_NOTIFICATIONS_ENABLED: current.get(
                    CONF_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED
                ),
                CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE)
                or current.get(CONF_NOTIFY_SERVICE)
                or "",
            }
            existing_map = dict(current.get(CONF_HARD_REBOOT_SWITCHES) or {})
            if user_input.get(CONF_CONFIGURE_HARD_SWITCHES) and daikin_entries:
                self._daikin_queue = daikin_entries
                self._hard_map = {}
                self._index = 0
                return await self.async_step_hard_switch()
            self._pending[CONF_HARD_REBOOT_SWITCHES] = existing_map
            return self.async_create_entry(title="", data=self._pending)

        notify_default = current.get(CONF_NOTIFY_SERVICE) or _guess_mobile_notify(self.hass)
        has_hard = bool(current.get(CONF_HARD_REBOOT_SWITCHES))
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_CHECK_INTERVAL,
                default=current.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            vol.Required(
                CONF_FAILURES_BEFORE_REBOOT,
                default=current.get(
                    CONF_FAILURES_BEFORE_REBOOT, DEFAULT_FAILURES_BEFORE_REBOOT
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Required(
                CONF_AUTO_REBOOT,
                default=current.get(CONF_AUTO_REBOOT, DEFAULT_AUTO_REBOOT),
            ): bool,
            vol.Required(
                CONF_REBOOT_COOLDOWN,
                default=current.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN),
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            vol.Required(
                CONF_MAX_SOFT_REBOOTS_PER_DAY,
                default=current.get(
                    CONF_MAX_SOFT_REBOOTS_PER_DAY, DEFAULT_MAX_SOFT_REBOOTS_PER_DAY
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
            vol.Required(
                CONF_HTTP_TIMEOUT,
                default=current.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT),
            ): vol.All(vol.Coerce(int), vol.Range(min=2, max=60)),
            vol.Required(
                CONF_HARD_REBOOT_OFF_SECONDS,
                default=current.get(
                    CONF_HARD_REBOOT_OFF_SECONDS, DEFAULT_HARD_REBOOT_OFF_SECONDS
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
            vol.Required(
                CONF_RELOAD_DAIKIN,
                default=current.get(CONF_RELOAD_DAIKIN, DEFAULT_RELOAD_DAIKIN),
            ): bool,
        }
        if notify_default:
            schema[vol.Optional(CONF_NOTIFY_SERVICE, default=notify_default)] = (
                _notify_selector()
            )
        else:
            schema[vol.Optional(CONF_NOTIFY_SERVICE)] = _notify_selector()
        schema[
            vol.Optional(CONF_CONFIGURE_HARD_SWITCHES, default=has_hard)
        ] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "daikin_count": str(len(daikin_entries)),
            },
        )

    async def async_step_hard_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._daikin_queue[self._index]
        current_map = (self._current_options().get(CONF_HARD_REBOOT_SWITCHES) or {})
        if user_input is not None:
            value = user_input.get(CONF_HARD_REBOOT_SWITCH)
            if value:
                self._hard_map[entry.entry_id] = value
            self._index += 1
            if self._index < len(self._daikin_queue):
                return await self.async_step_hard_switch()
            self._pending[CONF_HARD_REBOOT_SWITCHES] = self._hard_map
            return self.async_create_entry(title="", data=self._pending)

        default = current_map.get(entry.entry_id)
        schema: dict[Any, Any]
        if default:
            schema = {
                vol.Optional(CONF_HARD_REBOOT_SWITCH, default=default): _switch_selector()
            }
        else:
            schema = {vol.Optional(CONF_HARD_REBOOT_SWITCH): _switch_selector()}
        return self.async_show_form(
            step_id="hard_switch",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "name": entry.title or entry.entry_id,
                "host": str(entry.data.get(CONF_HOST) or ""),
            },
        )
