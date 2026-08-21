"""Daikin WiFi Watchdog — monitors official Daikin AC integration modules."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_OFF_SECONDS,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_REBOOT_COOLDOWN,
    CONF_RELOAD_DAIKIN,
    CONF_WATCHDOG_ENABLED,
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
    PLATFORMS,
    SERVICE_CHECK_NOW,
    SERVICE_HARD_REBOOT,
    SERVICE_REBOOT,
)
from .coordinator import DaikinWatchdogCoordinator

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
        CONF_HARD_REBOOT_OFF_SECONDS: DEFAULT_HARD_REBOOT_OFF_SECONDS,
        CONF_WATCHDOG_ENABLED: DEFAULT_WATCHDOG_ENABLED,
        CONF_NOTIFICATIONS_ENABLED: DEFAULT_NOTIFICATIONS_ENABLED,
        CONF_NOTIFY_SERVICE: "",
        CONF_RELOAD_DAIKIN: DEFAULT_RELOAD_DAIKIN,
    }


def _register_services(hass: HomeAssistant) -> None:
    async def _handle_reboot(call: ServiceCall) -> None:
        coordinator = _coordinator_from_hass(hass)
        await coordinator.async_reboot_module(
            entry_id=call.data.get("entry_id"),
            host=call.data.get(CONF_HOST),
        )

    async def _handle_hard_reboot(call: ServiceCall) -> None:
        coordinator = _coordinator_from_hass(hass)
        await coordinator.async_hard_reboot_module(
            entry_id=call.data.get("entry_id"),
            host=call.data.get(CONF_HOST),
        )

    async def _handle_check_now(_call: ServiceCall) -> None:
        coordinator = _coordinator_from_hass(hass)
        await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_REBOOT):
        hass.services.async_register(
            DOMAIN, SERVICE_REBOOT, _handle_reboot, schema=REBOOT_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_HARD_REBOOT):
        hass.services.async_register(
            DOMAIN, SERVICE_HARD_REBOOT, _handle_hard_reboot, schema=REBOOT_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CHECK_NOW):
        hass.services.async_register(DOMAIN, SERVICE_CHECK_NOW, _handle_check_now)


def _coordinator_from_hass(hass: HomeAssistant) -> DaikinWatchdogCoordinator:
    stored = hass.data.get(DOMAIN) or {}
    if not stored:
        raise ValueError("Daikin WiFi Watchdog is not loaded")
    return next(iter(stored.values()))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    options = {**default_options(), **(entry.options or {})}
    coordinator = DaikinWatchdogCoordinator(hass, options, config_entry=entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.runtime_data = coordinator

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(
        hass.config_entries.async_add_listener(coordinator.async_on_ha_config_entries_changed)
    )
    _register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    options = {**default_options(), **(entry.options or {})}
    coordinator.update_options(options)
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown_watchdog()
        if not hass.data[DOMAIN]:
            for service in (SERVICE_REBOOT, SERVICE_HARD_REBOOT, SERVICE_CHECK_NOW):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
            hass.data.pop(DOMAIN, None)
    return unload_ok
