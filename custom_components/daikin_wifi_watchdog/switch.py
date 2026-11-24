"""Global enable switches for the watchdog hub."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .climate_manager import ClimateManager
from .const import (
    CONF_NOTIFICATIONS_ENABLED,
    CONF_WATCHDOG_ENABLED,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
    SIGNAL_CLIMATE_UPDATED,
)
from .coordinator import DaikinWatchdogCoordinator
from .helpers import integration_version

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

AUTO_HEAT_SWITCH = SwitchEntityDescription(
    key="auto_heat",
    translation_key="auto_heat",
    icon="mdi:radiator",
)

AUTO_COOL_SWITCH = SwitchEntityDescription(
    key="auto_cool",
    translation_key="auto_cool",
    icon="mdi:snowflake-thermometer",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    climate: ClimateManager = coordinator.climate
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
            DaikinAutoHeatSwitch(coordinator, entry, climate, AUTO_HEAT_SWITCH),
            DaikinAutoCoolSwitch(coordinator, entry, climate, AUTO_COOL_SWITCH),
        ]
    )


def _hub_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Daikin WiFi Watchdog",
        manufacturer="Daikin",
        model="WiFi Watchdog",
        sw_version=integration_version(),
        configuration_url="https://github.com/nicdive/daikin-HA-watchdog",
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
        self._attr_device_info = _hub_device_info(entry)
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


class DaikinAutoHeatSwitch(SwitchEntity):
    """AUTO chauffage — drives heat scenes from sensors + presence."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        climate: ClimateManager,
        description: SwitchEntityDescription,
    ) -> None:
        self.entity_description = description
        self.coordinator = coordinator
        self._climate = climate
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = _hub_device_info(entry)
        self.entity_id = f"switch.{DOMAIN}_{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CLIMATE_UPDATED, _updated)
        )

    @property
    def available(self) -> bool:
        return self._climate.enabled

    @property
    def is_on(self) -> bool:
        return self._climate.auto_heat

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._climate.async_set_auto_heat(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._climate.async_set_auto_heat(False)
        self.async_write_ha_state()


class DaikinAutoCoolSwitch(SwitchEntity):
    """AUTO clim — drives cool scenes from sensors + presence."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        climate: ClimateManager,
        description: SwitchEntityDescription,
    ) -> None:
        self.entity_description = description
        self.coordinator = coordinator
        self._climate = climate
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_device_info = _hub_device_info(entry)
        self.entity_id = f"switch.{DOMAIN}_{description.key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CLIMATE_UPDATED, _updated)
        )

    @property
    def available(self) -> bool:
        return self._climate.enabled

    @property
    def is_on(self) -> bool:
        return self._climate.auto_cool

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._climate.async_set_auto_cool(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._climate.async_set_auto_cool(False)
        self.async_write_ha_state()
