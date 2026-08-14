"""Button to manually reboot a WiFi module."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator
from .entity import DaikinWatchdogEntity

DESCRIPTION = ButtonEntityDescription(
    key="reboot_wifi",
    name="Reboot WiFi module",
    icon="mdi:restart-alert",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    known: set[str] = set()

    @callback
    def _add_entities() -> None:
        new: list[DaikinWifiRebootButton] = []
        for daikin_entry_id in (coordinator.data or {}):
            if daikin_entry_id in known:
                continue
            known.add(daikin_entry_id)
            new.append(DaikinWifiRebootButton(coordinator, daikin_entry_id))
        if new:
            async_add_entities(new)

    _add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_entities))


class DaikinWifiRebootButton(DaikinWatchdogEntity, ButtonEntity):
    entity_description = DESCRIPTION

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, DESCRIPTION.key)

    async def async_press(self) -> None:
        await self.coordinator.async_reboot_module(entry_id=self._daikin_entry_id)
