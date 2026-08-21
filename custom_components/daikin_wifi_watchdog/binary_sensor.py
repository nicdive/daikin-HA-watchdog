"""Binary sensors for module health."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator
from .entity import DaikinWatchdogEntity

DESCRIPTION = BinarySensorEntityDescription(
    key="healthy",
    translation_key="healthy",
    icon="mdi:wifi-check",
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
        new: list[DaikinWifiHealthySensor] = []
        for daikin_entry_id in coordinator.data or {}:
            if daikin_entry_id in known:
                continue
            known.add(daikin_entry_id)
            new.append(DaikinWifiHealthySensor(coordinator, daikin_entry_id))
        if new:
            async_add_entities(new)

    _add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_entities))


class DaikinWifiHealthySensor(DaikinWatchdogEntity, BinarySensorEntity):
    """On when the module answers and err is not an unhealthy code."""

    entity_description = DESCRIPTION

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(
            coordinator,
            daikin_entry_id,
            DESCRIPTION.key,
            translation_key=DESCRIPTION.translation_key,
        )

    @property
    def is_on(self) -> bool | None:
        snap = self.snapshot
        if snap is None:
            return None
        return snap.healthy

    @property
    def extra_state_attributes(self) -> dict | None:
        snap = self.snapshot
        return snap.attributes if snap else None
