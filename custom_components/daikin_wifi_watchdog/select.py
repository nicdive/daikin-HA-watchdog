"""Global heating / cooling mode selects on the watchdog hub."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .climate_defaults import COOL_MODES, HEAT_MODES
from .climate_manager import ClimateManager
from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator
from .helpers import integration_version

HEAT_SELECT = SelectEntityDescription(
    key="heat_mode",
    translation_key="heat_mode",
    icon="mdi:radiator",
)

COOL_SELECT = SelectEntityDescription(
    key="cool_mode",
    translation_key="cool_mode",
    icon="mdi:snowflake",
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
            DaikinHeatModeSelect(coordinator, entry, climate, HEAT_SELECT),
            DaikinCoolModeSelect(coordinator, entry, climate, COOL_SELECT),
        ]
    )


class _HubSelectBase(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        climate: ClimateManager,
        description: SelectEntityDescription,
        options: tuple[str, ...],
    ) -> None:
        self.entity_description = description
        self.coordinator = coordinator
        self._entry = entry
        self._climate = climate
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self._attr_options = list(options)
        # Stable entity_id (independent of HA language at first setup).
        self.entity_id = f"select.{DOMAIN}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Daikin WiFi Watchdog",
            manufacturer="Daikin",
            model="WiFi Watchdog",
            sw_version=integration_version(),
            configuration_url="https://github.com/nicdive/daikin-HA-watchdog",
        )

    @property
    def available(self) -> bool:
        return self._climate.enabled


class DaikinHeatModeSelect(_HubSelectBase):
    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        climate: ClimateManager,
        description: SelectEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry, climate, description, HEAT_MODES)

    @property
    def current_option(self) -> str | None:
        return self._climate.heat_mode

    async def async_select_option(self, option: str) -> None:
        await self._climate.async_set_heat_mode(option)
        self.async_write_ha_state()


class DaikinCoolModeSelect(_HubSelectBase):
    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        climate: ClimateManager,
        description: SelectEntityDescription,
    ) -> None:
        super().__init__(coordinator, entry, climate, description, COOL_MODES)

    @property
    def current_option(self) -> str | None:
        return self._climate.cool_mode

    async def async_select_option(self, option: str) -> None:
        await self._climate.async_set_cool_mode(option)
        self.async_write_ha_state()
