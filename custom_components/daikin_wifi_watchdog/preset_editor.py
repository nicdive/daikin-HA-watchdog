"""Dashboard-facing editor for heating / cooling scene setpoints."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .climate_defaults import (
    COOL_MODES,
    DAIKIN_MODE_COOL,
    DAIKIN_MODE_DRY,
    DAIKIN_MODE_HEAT,
    DEFAULT_COOL_PRESETS,
    DEFAULT_HEAT_PRESETS,
    DIR_BOTH,
    DeviceSetpoint,
    FAN_AUTO,
    FAN_DIR_OPTIONS,
    FAN_RATE_OPTIONS,
    HEAT_MODES,
    match_device_key,
    presets_from_dict,
    presets_to_dict,
)
from .const import (
    CONF_COOL_PRESETS,
    CONF_HEAT_PRESETS,
    DAIKIN_DOMAIN,
    SIGNAL_CLIMATE_UPDATED,
)
from .coordinator import DaikinWatchdogCoordinator
from .helpers import daikin_entry_display_name

_LOGGER = logging.getLogger(__name__)

PROGRAM_DOMAINS = ("heat", "cool")
SIGNAL_PRESET_EDITOR_UPDATED = "daikin_wifi_watchdog_preset_editor_updated"

FAN_RATE_LABELS = {
    "A": "Auto",
    "B": "Silence",
    "3": "Débit 1",
    "4": "Débit 2",
    "5": "Débit 3",
    "6": "Débit 4",
    "7": "Débit 5",
}
FAN_DIR_LABELS = {
    "0": "Arrêt",
    "1": "Verticale",
    "2": "Horizontale",
    "3": "Verticale + horizontale",
}


class PresetEditor:
    """Pick one domain/scene/device and edit its stored setpoint."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: DaikinWatchdogCoordinator,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.domain = "heat"
        self.scene = "confort"
        self.device_entry_id: str | None = None
        self._persist_lock = False

    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_PRESET_EDITOR_UPDATED)
        async_dispatcher_send(self.hass, SIGNAL_CLIMATE_UPDATED)

    def ensure_selection(self) -> None:
        """Pick defaults when empty or stale."""
        devices = self.device_choices()
        if not devices:
            self.device_entry_id = None
            return
        ids = {entry_id for entry_id, _ in devices}
        if self.device_entry_id not in ids:
            self.device_entry_id = devices[0][0]
        scenes = self.scene_options()
        if self.scene not in scenes:
            self.scene = scenes[0] if scenes else "confort"
        if self.domain not in PROGRAM_DOMAINS:
            self.domain = "heat"

    def device_choices(self) -> list[tuple[str, str]]:
        """Return (entry_id, friendly label) for every Daikin AC."""
        choices: list[tuple[str, str]] = []
        seen_labels: dict[str, int] = {}
        for daikin in self.hass.config_entries.async_entries(DAIKIN_DOMAIN):
            if daikin.source == config_entries.SOURCE_IGNORE:
                continue
            label = daikin_entry_display_name(self.hass, daikin)
            count = seen_labels.get(label, 0)
            seen_labels[label] = count + 1
            if count:
                host = str((daikin.data or {}).get("host") or "")[-7:]
                label = f"{label} ({host})" if host else f"{label} ({count + 1})"
            choices.append((daikin.entry_id, label))
        choices.sort(key=lambda item: item[1].casefold())
        return choices

    def scene_options(self) -> list[str]:
        modes = HEAT_MODES if self.domain == "heat" else COOL_MODES
        return [mode for mode in modes if mode != "off"]

    def _raw_presets(self) -> dict[str, Any]:
        key = CONF_HEAT_PRESETS if self.domain == "heat" else CONF_COOL_PRESETS
        defaults = (
            DEFAULT_HEAT_PRESETS if self.domain == "heat" else DEFAULT_COOL_PRESETS
        )
        options = dict(self.entry.options or {})
        return presets_to_dict(
            presets_from_dict(options.get(key), defaults)  # type: ignore[arg-type]
        )

    def _daikin_entry(self) -> ConfigEntry | None:
        if not self.device_entry_id:
            return None
        return self.hass.config_entries.async_get_entry(self.device_entry_id)

    def current_setpoint(self) -> DeviceSetpoint:
        self.ensure_selection()
        presets = self._raw_presets()
        devices = dict(presets.get(self.scene) or {})
        entry_id = self.device_entry_id
        if entry_id and entry_id in devices:
            return DeviceSetpoint.from_dict(devices[entry_id])

        daikin = self._daikin_entry()
        host = str((daikin.data or {}).get("host") or "") if daikin else ""
        title = str(daikin.title or "") if daikin else ""
        if host and host in devices:
            return DeviceSetpoint.from_dict(devices[host])
        device_key = match_device_key(host, title)
        if device_key and device_key in devices:
            return DeviceSetpoint.from_dict(devices[device_key])
        default_mode = DAIKIN_MODE_HEAT if self.domain == "heat" else DAIKIN_MODE_COOL
        if self.domain == "cool" and self.scene == "dry":
            default_mode = DAIKIN_MODE_DRY
        return DeviceSetpoint(power=False, mode=default_mode)

    async def async_set_domain(self, domain: str) -> None:
        if domain not in PROGRAM_DOMAINS:
            return
        self.domain = domain
        scenes = self.scene_options()
        if self.scene not in scenes:
            self.scene = scenes[0] if scenes else self.scene
        self.ensure_selection()
        self._notify()

    async def async_set_scene(self, scene: str) -> None:
        if scene not in self.scene_options():
            return
        self.scene = scene
        self._notify()

    async def async_set_device(self, entry_id: str) -> None:
        ids = {eid for eid, _ in self.device_choices()}
        if entry_id not in ids:
            return
        self.device_entry_id = entry_id
        self._notify()

    async def async_set_power(self, power: bool) -> None:
        sp = self.current_setpoint()
        await self._async_write_setpoint(
            DeviceSetpoint(
                power=power,
                temp=sp.temp if power else None,
                mode=sp.mode,
                fan_rate=sp.fan_rate,
                fan_dir=sp.fan_dir,
            )
        )

    async def async_set_temperature(self, temp: float) -> None:
        sp = self.current_setpoint()
        await self._async_write_setpoint(
            DeviceSetpoint(
                power=True,
                temp=float(temp),
                mode=sp.mode,
                fan_rate=sp.fan_rate,
                fan_dir=sp.fan_dir,
            )
        )

    async def async_set_fan_rate(self, fan_rate: str) -> None:
        if fan_rate not in FAN_RATE_OPTIONS:
            return
        sp = self.current_setpoint()
        await self._async_write_setpoint(
            DeviceSetpoint(
                power=sp.power,
                temp=sp.temp,
                mode=sp.mode,
                fan_rate=fan_rate,
                fan_dir=sp.fan_dir,
            )
        )

    async def async_set_fan_dir(self, fan_dir: str) -> None:
        if fan_dir not in FAN_DIR_OPTIONS:
            return
        sp = self.current_setpoint()
        await self._async_write_setpoint(
            DeviceSetpoint(
                power=sp.power,
                temp=sp.temp,
                mode=sp.mode,
                fan_rate=sp.fan_rate,
                fan_dir=fan_dir,
            )
        )

    async def _async_write_setpoint(self, setpoint: DeviceSetpoint) -> None:
        self.ensure_selection()
        if not self.device_entry_id or not self.scene:
            return

        # Keep HVAC mode coherent with domain / dry scene.
        if self.domain == "heat":
            mode = DAIKIN_MODE_HEAT
        elif self.scene == "dry":
            mode = DAIKIN_MODE_DRY
        else:
            mode = DAIKIN_MODE_COOL
        if not setpoint.power:
            setpoint = DeviceSetpoint(
                power=False,
                temp=None,
                mode=mode,
                fan_rate=FAN_AUTO,
                fan_dir=DIR_BOTH,
            )
        else:
            setpoint = DeviceSetpoint(
                power=True,
                temp=setpoint.temp,
                mode=mode,
                fan_rate=setpoint.fan_rate or FAN_AUTO,
                fan_dir=setpoint.fan_dir or DIR_BOTH,
            )

        key = CONF_HEAT_PRESETS if self.domain == "heat" else CONF_COOL_PRESETS
        presets = self._raw_presets()
        scene_map = dict(presets.get(self.scene) or {})
        scene_map[self.device_entry_id] = setpoint.to_dict()
        # Also keep the room slug key in sync when we know it.
        daikin = self._daikin_entry()
        if daikin:
            host = str((daikin.data or {}).get("host") or "")
            title = str(daikin.title or "")
            device_key = match_device_key(host, title)
            if device_key:
                scene_map[device_key] = setpoint.to_dict()
        presets[self.scene] = scene_map

        options = {**dict(self.entry.options or {}), key: presets}
        self._persist_lock = True
        try:
            self.hass.config_entries.async_update_entry(self.entry, options=options)
            climate = getattr(self.coordinator, "climate", None)
            if climate is not None:
                climate.update_options({**climate.options, key: presets})
            await self._async_apply_if_active(setpoint)
        finally:
            self._persist_lock = False
        self._notify()
        _LOGGER.debug(
            "Preset saved: %s/%s/%s power=%s temp=%s fan=%s dir=%s",
            self.domain,
            self.scene,
            self.device_entry_id,
            setpoint.power,
            setpoint.temp,
            setpoint.fan_rate,
            setpoint.fan_dir,
        )

    async def _async_apply_if_active(self, setpoint: DeviceSetpoint) -> None:
        """Push to the live unit when this scene is currently active."""
        climate = getattr(self.coordinator, "climate", None)
        if climate is None or not climate.enabled:
            return
        active = (
            climate.heat_mode
            if self.domain == "heat"
            else climate.cool_mode
        )
        if active != self.scene:
            return
        modules = self.coordinator.discover_modules()
        module = next(
            (m for m in modules if m.entry_id == self.device_entry_id),
            None,
        )
        if module is None or module.disabled:
            return
        await climate._async_apply_setpoint(module, setpoint)  # noqa: SLF001

    @callback
    def on_options_updated(self) -> None:
        """Refresh listeners after options reload (skip our own write)."""
        if self._persist_lock:
            return
        self.ensure_selection()
        self._notify()
