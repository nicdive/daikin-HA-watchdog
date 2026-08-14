"""Config flow for Daikin WiFi Watchdog."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_REBOOT_COOLDOWN,
    DAIKIN_DOMAIN,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_REBOOT_COOLDOWN,
    DOMAIN,
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
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CHECK_INTERVAL, default=DEFAULT_CHECK_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
                    vol.Required(
                        CONF_FAILURES_BEFORE_REBOOT,
                        default=DEFAULT_FAILURES_BEFORE_REBOOT,
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
                    vol.Required(CONF_AUTO_REBOOT, default=DEFAULT_AUTO_REBOOT): bool,
                }
            ),
            description_placeholders={
                "daikin_count": str(len(daikin_entries)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return DaikinWifiWatchdogOptionsFlow()


class DaikinWifiWatchdogOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Options flow including optional hard-reboot switch mapping."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self.options
        daikin_entries = self.hass.config_entries.async_entries(DAIKIN_DOMAIN)

        if user_input is not None:
            hard_map: dict[str, str] = {}
            for entry in daikin_entries:
                key = f"hard_switch_{entry.entry_id}"
                value = user_input.get(key)
                if value:
                    hard_map[entry.entry_id] = value

            return self.async_create_entry(
                title="",
                data={
                    CONF_CHECK_INTERVAL: user_input[CONF_CHECK_INTERVAL],
                    CONF_FAILURES_BEFORE_REBOOT: user_input[CONF_FAILURES_BEFORE_REBOOT],
                    CONF_AUTO_REBOOT: user_input[CONF_AUTO_REBOOT],
                    CONF_REBOOT_COOLDOWN: user_input[CONF_REBOOT_COOLDOWN],
                    CONF_MAX_SOFT_REBOOTS_PER_DAY: user_input[
                        CONF_MAX_SOFT_REBOOTS_PER_DAY
                    ],
                    CONF_HTTP_TIMEOUT: user_input[CONF_HTTP_TIMEOUT],
                    CONF_HARD_REBOOT_SWITCHES: hard_map,
                },
            )

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
        }

        hard_current = current.get(CONF_HARD_REBOOT_SWITCHES) or {}
        for entry in daikin_entries:
            default = hard_current.get(entry.entry_id)
            key = f"hard_switch_{entry.entry_id}"
            if default:
                schema[vol.Optional(key, default=default)] = selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch", multiple=False)
                )
            else:
                schema[vol.Optional(key)] = selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch", multiple=False)
                )

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
