"""Sensors for watchdog status."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STATUS_OPTIONS
from .coordinator import DaikinWatchdogCoordinator
from .entity import DaikinWatchdogEntity

STATUS = SensorEntityDescription(
    key="wifi_status",
    translation_key="wifi_status",
    icon="mdi:wifi",
    device_class=SensorDeviceClass.ENUM,
    options=STATUS_OPTIONS,
)

ERROR_CODE = SensorEntityDescription(
    key="wifi_error_code",
    translation_key="wifi_error_code",
    icon="mdi:alert-circle-outline",
    entity_category=EntityCategory.DIAGNOSTIC,
)

LAST_REBOOT = SensorEntityDescription(
    key="wifi_last_reboot",
    translation_key="wifi_last_reboot",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)

REBOOTS_TODAY = SensorEntityDescription(
    key="wifi_soft_reboots_today",
    translation_key="wifi_soft_reboots_today",
    icon="mdi:restart",
    state_class=SensorStateClass.TOTAL,
    entity_category=EntityCategory.DIAGNOSTIC,
)

FAILURES = SensorEntityDescription(
    key="wifi_consecutive_failures",
    translation_key="wifi_consecutive_failures",
    icon="mdi:counter",
    state_class=SensorStateClass.MEASUREMENT,
    entity_category=EntityCategory.DIAGNOSTIC,
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
        for daikin_entry_id in coordinator.data or {}:
            if daikin_entry_id in known:
                continue
            known.add(daikin_entry_id)
            new.extend(
                [
                    DaikinWifiStatusSensor(coordinator, daikin_entry_id),
                    DaikinWifiErrorCodeSensor(coordinator, daikin_entry_id),
                    DaikinWifiLastRebootSensor(coordinator, daikin_entry_id),
                    DaikinWifiRebootsTodaySensor(coordinator, daikin_entry_id),
                    DaikinWifiFailuresSensor(coordinator, daikin_entry_id),
                ]
            )
        if new:
            async_add_entities(new)

    _add_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_entities))


class _WatchdogSensor(DaikinWatchdogEntity, SensorEntity):
    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        daikin_entry_id: str,
        description: SensorEntityDescription,
    ) -> None:
        super().__init__(
            coordinator,
            daikin_entry_id,
            description.key,
            translation_key=description.translation_key,
        )
        self.entity_description = description


class DaikinWifiStatusSensor(_WatchdogSensor):
    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, STATUS)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.status if snap else None

    @property
    def extra_state_attributes(self) -> dict | None:
        snap = self.snapshot
        return snap.attributes if snap else None


class DaikinWifiErrorCodeSensor(_WatchdogSensor):
    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, ERROR_CODE)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.error_code if snap else None


class DaikinWifiLastRebootSensor(_WatchdogSensor):
    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, LAST_REBOOT)

    @property
    def native_value(self):
        snap = self.snapshot
        if snap is None or snap.last_reboot is None:
            return None
        if snap.last_reboot.tzinfo is None:
            return snap.last_reboot.replace(tzinfo=dt_util.UTC)
        return snap.last_reboot


class DaikinWifiRebootsTodaySensor(_WatchdogSensor):
    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, REBOOTS_TODAY)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.soft_reboots_today if snap else None


class DaikinWifiFailuresSensor(_WatchdogSensor):
    def __init__(
        self, coordinator: DaikinWatchdogCoordinator, daikin_entry_id: str
    ) -> None:
        super().__init__(coordinator, daikin_entry_id, FAILURES)

    @property
    def native_value(self) -> StateType:
        snap = self.snapshot
        return snap.consecutive_failures if snap else None
