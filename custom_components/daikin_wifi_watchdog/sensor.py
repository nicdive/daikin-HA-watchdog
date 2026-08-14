"""Sensors for watchdog status."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator
from .entity import DaikinWatchdogEntity

STATUS = SensorEntityDescription(
    key="wifi_status",
    name="WiFi status",
    icon="mdi:wifi",
)

ERROR_CODE = SensorEntityDescription(
    key="wifi_error_code",
    name="WiFi error code",
    icon="mdi:alert-circle-outline",
)

LAST_REBOOT = SensorEntityDescription(
    key="wifi_last_reboot",
    name="WiFi last reboot",
    device_class=SensorDeviceClass.TIMESTAMP,
)

REBOOTS_TODAY = SensorEntityDescription(
    key="wifi_soft_reboots_today",
    name="WiFi soft reboots today",
    icon="mdi:restart",
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
        new: list[SensorEntity] = []
        for daikin_entry_id in (coordinator.data or {}):
            if daikin_entry_id in known:
                continue
            known.add(daikin_entry_id)
            new.extend(
                [
                    DaikinWifiStatusSensor(coordinator, daikin_entry_id),
                    DaikinWifiErrorCodeSensor(coordinator, daikin_entry_id),
                    DaikinWifiLastRebootSensor(coordinator, daikin_entry_id),
                    DaikinWifiRebootsTodaySensor(coordinator, daikin_entry_id),
                ]
            )
        if new:
            async_add_entities(new)

    _add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_entities))


class DaikinWifiStatusSensor(DaikinWatchdogEntity, SensorEntity):
    entity_description = STATUS

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, STATUS.key)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.status if snap else None

    @property
    def extra_state_attributes(self) -> dict | None:
        snap = self.snapshot
        return snap.attributes if snap else None


class DaikinWifiErrorCodeSensor(DaikinWatchdogEntity, SensorEntity):
    entity_description = ERROR_CODE

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, ERROR_CODE.key)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.error_code if snap else None


class DaikinWifiLastRebootSensor(DaikinWatchdogEntity, SensorEntity):
    entity_description = LAST_REBOOT

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, LAST_REBOOT.key)

    @property
    def native_value(self):
        snap = self.snapshot
        return snap.last_reboot if snap else None


class DaikinWifiRebootsTodaySensor(DaikinWatchdogEntity, SensorEntity):
    entity_description = REBOOTS_TODAY

    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, REBOOTS_TODAY.key)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.soft_reboots_today if snap else None
