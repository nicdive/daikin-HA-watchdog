"""Daikin WiFi Watchdog — monitors official Daikin AC integration modules."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_REBOOT_COOLDOWN,
    CONF_WATCHDOG_ENABLED,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_REBOOT_COOLDOWN,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
    PLATFORMS,
    SERVICE_CHECK_NOW,
    SERVICE_REBOOT,
)
from .coordinator import DaikinWatchdogCoordinator

_LOGGER = logging.getLogger(__name__)

REBOOT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional(CONF_HOST): cv.string,
    }
)


def default_options() -> dict[str, Any]:
    return {
        CONF_CHECK_INTERVAL: DEFAULT_CHECK_INTERVAL,
        CONF_FAILURES_BEFORE_REBOOT: DEFAULT_FAILURES_BEFORE_REBOOT,
        CONF_AUTO_REBOOT: DEFAULT_AUTO_REBOOT,
        CONF_REBOOT_COOLDOWN: DEFAULT_REBOOT_COOLDOWN,
        CONF_MAX_SOFT_REBOOTS_PER_DAY: DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
        CONF_HTTP_TIMEOUT: DEFAULT_HTTP_TIMEOUT,
        CONF_HARD_REBOOT_SWITCHES: {},
        CONF_WATCHDOG_ENABLED: DEFAULT_WATCHDOG_ENABLED,
        CONF_NOTIFICATIONS_ENABLED: DEFAULT_NOTIFICATIONS_ENABLED,
        CONF_NOTIFY_SERVICE: "",
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    options = {**default_options(), **(entry.options or {})}
    coordinator = DaikinWatchdogCoordinator(hass, options)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    async def _first_refresh(_event=None) -> None:
        await coordinator.async_refresh()

    if hass.is_running:
        await coordinator.async_config_entry_first_refresh()
    else:
        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _first_refresh)
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _handle_reboot(call: ServiceCall) -> None:
        await coordinator.async_reboot_module(
            entry_id=call.data.get("entry_id"),
            host=call.data.get(CONF_HOST),
        )

    async def _handle_check_now(_call: ServiceCall) -> None:
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_REBOOT, _handle_reboot, schema=REBOOT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CHECK_NOW, _handle_check_now)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    options = {**default_options(), **(entry.options or {})}
    coordinator.update_options(options)
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_REBOOT)
            hass.services.async_remove(DOMAIN, SERVICE_CHECK_NOW)
            hass.data.pop(DOMAIN, None)
    return unload_ok
