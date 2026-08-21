"""Diagnostics for Daikin WiFi Watchdog."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_PASSWORD, CONF_UUID
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import CONF_NOTIFY_SERVICE, DOMAIN
from .coordinator import DaikinWatchdogCoordinator

TO_REDACT = {
    CONF_API_KEY,
    CONF_PASSWORD,
    CONF_UUID,
    CONF_NOTIFY_SERVICE,
    "lpw",
    "password",
    "uuid",
    "api_key",
}


def _coordinator(hass: HomeAssistant, entry: ConfigEntry) -> DaikinWatchdogCoordinator:
    stored = hass.data.get(DOMAIN, {})
    coordinator = stored.get(entry.entry_id)
    if coordinator is not None:
        return coordinator
    return entry.runtime_data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = _coordinator(hass, entry)
    snapshots = [
        coordinator.snapshot_as_dict(snap)
        for snap in (coordinator.data or {}).values()
    ]
    return async_redact_data(
        {
            "options": dict(entry.options or {}),
            "watchdog_enabled": coordinator.options.get("watchdog_enabled"),
            "module_count": len(coordinator.discover_modules()),
            "snapshots": snapshots,
            "last_update_success": coordinator.last_update_success,
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a watchdog device."""
    coordinator = _coordinator(hass, entry)
    for ident_domain, ident_id in device.identifiers:
        if ident_domain != DOMAIN:
            continue
        snap = (coordinator.data or {}).get(ident_id)
        if snap is None:
            continue
        return async_redact_data(coordinator.snapshot_as_dict(snap), TO_REDACT)
    return await async_get_config_entry_diagnostics(hass, entry)
