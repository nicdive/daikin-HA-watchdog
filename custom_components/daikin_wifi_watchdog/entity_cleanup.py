"""Remove leftover entity-registry rows from older watchdog versions."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_HARD_REBOOT_SWITCHES
from .coordinator import DaikinWatchdogCoordinator

# Longest unique_id suffixes first.
_MODULE_UNIQUE_SUFFIXES = (
    "wifi_consecutive_failures",
    "wifi_soft_reboots_today",
    "wifi_last_reboot",
    "wifi_error_code",
    "wifi_status",
    "hard_reboot_wifi",
    "reboot_wifi",
    "healthy",
)

_HUB_UNIQUE_SUFFIXES = frozenset(
    {
        "watchdog_enabled",
        "notifications_enabled",
    }
)


def _split_unique_id(unique_id: str) -> tuple[str, str] | None:
    for suffix in _MODULE_UNIQUE_SUFFIXES:
        ending = f"_{suffix}"
        if unique_id.endswith(ending):
            return unique_id[: -len(ending)], suffix
    for suffix in _HUB_UNIQUE_SUFFIXES:
        ending = f"_{suffix}"
        if unique_id.endswith(ending):
            return unique_id[: -len(ending)], suffix
    return None


def _has_hard_switch(coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str) -> bool:
    hard_map: dict[str, str] = coordinator.options.get(CONF_HARD_REBOOT_SWITCHES) or {}
    if hard_map.get(daikin_entry_id):
        return True
    snap = (coordinator.data or {}).get(daikin_entry_id)
    if snap is not None and hard_map.get(snap.module.host):
        return True
    return False


@callback
def async_cleanup_stale_entities(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: DaikinWatchdogCoordinator,
) -> None:
    """Drop restored/unavailable entities that this version no longer provides."""
    registry = er.async_get(hass)
    active_modules = set(coordinator.data or {})

    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        parsed = _split_unique_id(ent.unique_id)
        if parsed is None:
            continue
        owner_id, key = parsed
        if key in _HUB_UNIQUE_SUFFIXES:
            continue
        if key == "hard_reboot_wifi" and not _has_hard_switch(coordinator, owner_id):
            registry.async_remove(ent.entity_id)
            continue
        if owner_id not in active_modules:
            registry.async_remove(ent.entity_id)
