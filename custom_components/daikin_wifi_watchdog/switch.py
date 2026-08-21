"""Global enable switches for the watchdog hub."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_NOTIFICATIONS_ENABLED,
    CONF_WATCHDOG_ENABLED,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
)
from .coordinator import DaikinWatchdogCoordinator

WATCHDOG_SWITCH = SwitchEntityDescription(
    key="watchdog_enabled",
    translation_key="watchdog_enabled",
    icon="mdi:dog-service",
    entity_category=EntityCategory.CONFIG,
)

NOTIFICATIONS_SWITCH = SwitchEntityDescription(
    key="notifications_enabled",
    translation_key="notifications_enabled",
    icon="mdi:cellphone-message",
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            DaikinWatchdogToggleSwitch(
                coordinator,
                entry,
                WATCHDOG_SWITCH,
                CONF_WATCHDOG_ENABLED,
                DEFAULT_WATCHDOG_ENABLED,
            ),
            DaikinWatchdogToggleSwitch(
                coordinator,
                entry,
                NOTIFICATIONS_SWITCH,
                CONF_NOTIFICATIONS_ENABLED,
                DEFAULT_NOTIFICATIONS_ENABLED,
            ),
        ]
    )


class DaikinWatchdogToggleSwitch(SwitchEntity, RestoreEntity):
    """Persisted on/off switch stored in config entry options."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        description: SwitchEntityDescription,
        option_key: str,
        default: bool,
    ) -> None:
        self.entity_description = description
        self.coordinator = coordinator
        self._entry = entry
        self._option_key = option_key
        self._default = default
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Daikin WiFi Watchdog",
            manufacturer="Daikin",
            model="WiFi Watchdog",
            configuration_url="https://github.com/nicdive/daikin-HA-watchdog",
        )
        self._attr_is_on = bool(entry.options.get(option_key, default))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # Prefer persisted options; fall back to last HA state if option missing.
        if self._option_key not in self._entry.options:
            last = await self.async_get_last_state()
            if last is not None:
                self._attr_is_on = last.state == "on"
                await self._async_write_option(self._attr_is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        self._attr_is_on = value
        self.async_write_ha_state()
        await self._async_write_option(value)

    async def _async_write_option(self, value: bool) -> None:
        new_options = {**self._entry.options, self._option_key: value}
        self.hass.config_entries.async_update_entry(self._entry, options=new_options)
        self.coordinator.update_options({**self.coordinator.options, self._option_key: value})
        if self._option_key == CONF_WATCHDOG_ENABLED and value:
            await self.coordinator.async_request_refresh()
