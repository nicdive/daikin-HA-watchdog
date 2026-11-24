"""Global heating / cooling mode selects + program editor selects."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .climate_defaults import COOL_MODES, FAN_DIR_OPTIONS, FAN_RATE_OPTIONS, HEAT_MODES
from .climate_manager import ClimateManager
from .const import DOMAIN, SIGNAL_CLIMATE_UPDATED
from .coordinator import DaikinWatchdogCoordinator
from .helpers import integration_version
from .preset_editor import (
    PROGRAM_DOMAINS,
    SIGNAL_PRESET_EDITOR_UPDATED,
    PresetEditor,
)

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

PROGRAM_DOMAIN = SelectEntityDescription(
    key="program_domain",
    translation_key="program_domain",
    icon="mdi:thermometer-lines",
)

PROGRAM_SCENE = SelectEntityDescription(
    key="program_scene",
    translation_key="program_scene",
    icon="mdi:calendar-clock",
)

PROGRAM_DEVICE = SelectEntityDescription(
    key="program_device",
    translation_key="program_device",
    icon="mdi:hvac",
)

PROGRAM_FAN = SelectEntityDescription(
    key="program_fan",
    translation_key="program_fan",
    icon="mdi:fan",
)

PROGRAM_OSCILLATION = SelectEntityDescription(
    key="program_oscillation",
    translation_key="program_oscillation",
    icon="mdi:arrow-oscillating",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    climate: ClimateManager = coordinator.climate
    editor: PresetEditor = coordinator.preset_editor
    editor.ensure_selection()
    async_add_entities(
        [
            DaikinHeatModeSelect(coordinator, entry, climate, HEAT_SELECT),
            DaikinCoolModeSelect(coordinator, entry, climate, COOL_SELECT),
            ProgramDomainSelect(coordinator, entry, editor, PROGRAM_DOMAIN),
            ProgramSceneSelect(coordinator, entry, editor, PROGRAM_SCENE),
            ProgramDeviceSelect(coordinator, entry, editor, PROGRAM_DEVICE),
            ProgramFanSelect(coordinator, entry, editor, PROGRAM_FAN),
            ProgramOscillationSelect(coordinator, entry, editor, PROGRAM_OSCILLATION),
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
        self.entity_id = f"select.{DOMAIN}_{description.key}"
        self._attr_device_info = _hub_device_info(entry)

    @property
    def available(self) -> bool:
        return self._climate.enabled

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_CLIMATE_UPDATED, _updated)
        )


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


class _ProgramSelectBase(SelectEntity, RestoreEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        editor: PresetEditor,
        description: SelectEntityDescription,
    ) -> None:
        self.entity_description = description
        self.coordinator = coordinator
        self._entry = entry
        self._editor = editor
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self.entity_id = f"select.{DOMAIN}_{description.key}"
        self._attr_device_info = _hub_device_info(entry)

    @property
    def available(self) -> bool:
        climate = getattr(self.coordinator, "climate", None)
        return bool(climate and climate.enabled)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            await self._restore_option(last.state)

        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_PRESET_EDITOR_UPDATED, _updated
            )
        )

    async def _restore_option(self, option: str) -> None:
        """Optional restore hook for subclasses."""


class ProgramDomainSelect(_ProgramSelectBase):
    @property
    def options(self) -> list[str]:
        return list(PROGRAM_DOMAINS)

    @property
    def current_option(self) -> str | None:
        return self._editor.domain

    async def async_select_option(self, option: str) -> None:
        await self._editor.async_set_domain(option)

    async def _restore_option(self, option: str) -> None:
        if option in PROGRAM_DOMAINS:
            self._editor.domain = option
            self._editor.ensure_selection()


class ProgramSceneSelect(_ProgramSelectBase):
    @property
    def options(self) -> list[str]:
        return self._editor.scene_options()

    @property
    def current_option(self) -> str | None:
        self._editor.ensure_selection()
        return self._editor.scene

    async def async_select_option(self, option: str) -> None:
        await self._editor.async_set_scene(option)

    async def _restore_option(self, option: str) -> None:
        # Domain may not be restored yet; accept any known scene.
        if option in HEAT_MODES or option in COOL_MODES:
            if option != "off":
                self._editor.scene = option


class ProgramDeviceSelect(_ProgramSelectBase):
    @property
    def options(self) -> list[str]:
        return [label for _, label in self._editor.device_choices()]

    @property
    def current_option(self) -> str | None:
        self._editor.ensure_selection()
        for entry_id, label in self._editor.device_choices():
            if entry_id == self._editor.device_entry_id:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        for entry_id, label in self._editor.device_choices():
            if label == option:
                await self._editor.async_set_device(entry_id)
                return

    async def _restore_option(self, option: str) -> None:
        for entry_id, label in self._editor.device_choices():
            if label == option:
                self._editor.device_entry_id = entry_id
                return


class ProgramFanSelect(_ProgramSelectBase):
    @property
    def options(self) -> list[str]:
        return list(FAN_RATE_OPTIONS)

    @property
    def current_option(self) -> str | None:
        rate = self._editor.current_setpoint().fan_rate
        return rate if rate in FAN_RATE_OPTIONS else FAN_RATE_OPTIONS[0]

    async def async_select_option(self, option: str) -> None:
        await self._editor.async_set_fan_rate(option)


class ProgramOscillationSelect(_ProgramSelectBase):
    @property
    def options(self) -> list[str]:
        return list(FAN_DIR_OPTIONS)

    @property
    def current_option(self) -> str | None:
        direction = self._editor.current_setpoint().fan_dir
        return direction if direction in FAN_DIR_OPTIONS else "3"

    async def async_select_option(self, option: str) -> None:
        await self._editor.async_set_fan_dir(option)
