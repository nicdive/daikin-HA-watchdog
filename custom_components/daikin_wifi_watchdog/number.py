"""Program temperature setpoint editor on the watchdog hub."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator
from .helpers import integration_version
from .preset_editor import SIGNAL_PRESET_EDITOR_UPDATED, PresetEditor

PROGRAM_TEMP = NumberEntityDescription(
    key="program_temperature",
    translation_key="program_temperature",
    icon="mdi:thermometer",
    native_min_value=10,
    native_max_value=32,
    native_step=0.5,
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    editor: PresetEditor = coordinator.preset_editor
    async_add_entities([ProgramTemperatureNumber(coordinator, entry, editor, PROGRAM_TEMP)])


class ProgramTemperatureNumber(NumberEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        entry: ConfigEntry,
        editor: PresetEditor,
        description: NumberEntityDescription,
    ) -> None:
        self.entity_description = description
        self.coordinator = coordinator
        self._entry = entry
        self._editor = editor
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.translation_key
        self.entity_id = f"number.{DOMAIN}_{description.key}"
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
        climate = getattr(self.coordinator, "climate", None)
        return bool(climate and climate.enabled and self._editor.device_entry_id)

    @property
    def native_value(self) -> float:
        sp = self._editor.current_setpoint()
        if sp.temp is not None:
            return float(sp.temp)
        return 20.0 if self._editor.domain == "heat" else 27.0

    async def async_set_native_value(self, value: float) -> None:
        await self._editor.async_set_temperature(float(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _updated() -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_PRESET_EDITOR_UPDATED, _updated)
        )
