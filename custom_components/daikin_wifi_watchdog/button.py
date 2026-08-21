"""Buttons to manually reboot a WiFi module."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator
from .entity import DaikinWatchdogEntity

SOFT_REBOOT = ButtonEntityDescription(
    key="reboot_wifi",
    translation_key="reboot_wifi",
    icon="mdi:restart-alert",
    entity_category=EntityCategory.CONFIG,
)

HARD_REBOOT = ButtonEntityDescription(
    key="hard_reboot_wifi",
    translation_key="hard_reboot_wifi",
    icon="mdi:power-cycle",
    entity_category=EntityCategory.CONFIG,
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
        new: list[ButtonEntity] = []
        for daikin_entry_id in coordinator.data or {}:
            if daikin_entry_id in known:
                continue
            known.add(daikin_entry_id)
            new.append(DaikinWifiRebootButton(coordinator, daikin_entry_id))
            new.append(DaikinWifiHardRebootButton(coordinator, daikin_entry_id))
        if new:
            async_add_entities(new)

    _add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_entities))


class DaikinWifiRebootButton(DaikinWatchdogEntity, ButtonEntity):
    entity_description = SOFT_REBOOT

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(
            coordinator,
            daikin_entry_id,
            SOFT_REBOOT.key,
            translation_key=SOFT_REBOOT.translation_key,
        )

    async def async_press(self) -> None:
        await self.coordinator.async_reboot_module(entry_id=self._daikin_entry_id)


class DaikinWifiHardRebootButton(DaikinWatchdogEntity, ButtonEntity):
    entity_description = HARD_REBOOT

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(
            coordinator,
            daikin_entry_id,
            HARD_REBOOT.key,
            translation_key=HARD_REBOOT.translation_key,
        )

    @property
    def available(self) -> bool:
        snap = self.snapshot
        if snap is None:
            return False
        return bool(snap.attributes.get("has_hard_reboot_switch"))

    async def async_press(self) -> None:
        await self.coordinator.async_hard_reboot_module(entry_id=self._daikin_entry_id)
