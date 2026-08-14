"""Entity helpers."""

from __future__ import annotations

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DaikinWatchdogCoordinator, ModuleSnapshot


class DaikinWatchdogEntity(CoordinatorEntity[DaikinWatchdogCoordinator]):
    """Base entity bound to one discovered Daikin module."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DaikinWatchdogCoordinator,
        daikin_entry_id: str,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._daikin_entry_id = daikin_entry_id
        snap = self.snapshot
        module = snap.module if snap else None
        host = module.host if module else daikin_entry_id
        mac = module.mac if module else None
        title = module.title if module else host

        device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, daikin_entry_id)},
            "name": title,
            "manufacturer": "Daikin",
            "model": "WiFi module",
        }
        if mac:
            device_info["connections"] = {(dr.CONNECTION_NETWORK_MAC, mac)}
        if module:
            device_info["configuration_url"] = f"http://{host}/common/basic_info"
        self._attr_device_info = device_info
        self._attr_unique_id = f"{daikin_entry_id}_{key}"

    @property
    def snapshot(self) -> ModuleSnapshot | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._daikin_entry_id)

    @property
    def available(self) -> bool:
        return self.snapshot is not None
