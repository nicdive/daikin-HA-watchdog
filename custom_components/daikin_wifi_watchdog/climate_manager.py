"""Heating / cooling scene engine + AUTO rules (eedomus replacement)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .climate_defaults import (
    COOL_MODES,
    DEFAULT_COOL_OFF_OUTDOOR_BELOW,
    DEFAULT_COOL_ON_OUTDOOR_ABOVE,
    DEFAULT_COOL_ON_SALON_ABOVE,
    DEFAULT_COOL_PRESETS,
    DEFAULT_HEAT_OFF_OUTDOOR_ABOVE,
    DEFAULT_HEAT_OFF_SALON_ABOVE,
    DEFAULT_HEAT_ON_OUTDOOR_BELOW,
    DEFAULT_HEAT_ON_SALON_BELOW,
    DEFAULT_HEAT_PRESETS,
    DEFAULT_OPENING_DELAY_SECONDS,
    DeviceSetpoint,
    HEAT_MODES,
    match_device_key,
    presets_from_dict,
)
from .climate_rules import (
    desired_cool_mode,
    desired_heat_mode,
    is_night_hour,
    opening_is_blocking,
)
from .client import DaikinWifiClient
from .const import (
    CLIMATE_STORAGE_KEY,
    CLIMATE_STORAGE_VERSION,
    CONF_AUTO_COOL,
    CONF_AUTO_HEAT,
    CONF_CLIMATE_ENABLED,
    CONF_COOL_MODE,
    CONF_COOL_OFF_OUTDOOR_BELOW,
    CONF_COOL_ON_OUTDOOR_ABOVE,
    CONF_COOL_ON_SALON_ABOVE,
    CONF_COOL_PRESETS,
    CONF_HEAT_MODE,
    CONF_HEAT_OFF_OUTDOOR_ABOVE,
    CONF_HEAT_OFF_SALON_ABOVE,
    CONF_HEAT_ON_OUTDOOR_BELOW,
    CONF_HEAT_ON_SALON_BELOW,
    CONF_HEAT_PRESETS,
    CONF_NIGHT_END_HOUR,
    CONF_NIGHT_START_HOUR,
    CONF_OPENING_DELAY_SECONDS,
    CONF_OPENING_SENSORS,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_PRESENCE_SENSOR,
    CONF_SALON_TEMP_SENSOR,
    DEFAULT_AUTO_COOL,
    DEFAULT_AUTO_HEAT,
    DEFAULT_CLIMATE_ENABLED,
    DEFAULT_COOL_MODE,
    DEFAULT_HEAT_MODE,
    DEFAULT_NIGHT_END_HOUR,
    DEFAULT_NIGHT_START_HOUR,
    SIGNAL_CLIMATE_UPDATED,
)
from .coordinator import DaikinWatchdogCoordinator, TrackedModule

_LOGGER = logging.getLogger(__name__)

_PRESENCE_HOME = {STATE_HOME, STATE_ON, "present", "home", "true"}
_OPEN_STATES = {STATE_ON, "open", "opened"}


class ClimateManager:
    """Apply presets and evaluate AUTO chauffage / AUTO clim rules."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: DaikinWatchdogCoordinator,
        options: dict[str, Any],
        *,
        on_state_change: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self.options = dict(options)
        self._on_state_change = on_state_change
        self._store = Store(hass, CLIMATE_STORAGE_VERSION, CLIMATE_STORAGE_KEY)
        self._heat_mode = DEFAULT_HEAT_MODE
        self._cool_mode = DEFAULT_COOL_MODE
        self._auto_heat = DEFAULT_AUTO_HEAT
        self._auto_cool = DEFAULT_AUTO_COOL
        self._applying_auto = False
        self._opening_since: dict[str, datetime] = {}
        self._last_applied_heat: str | None = None
        self._last_applied_cool: str | None = None
        self._unsub_interval: Callable[[], None] | None = None
        self._unsub_states: Callable[[], None] | None = None
        self._loaded = False
        self._lock = asyncio.Lock()
        self._eval_seq = 0

    @property
    def enabled(self) -> bool:
        return bool(self.options.get(CONF_CLIMATE_ENABLED, DEFAULT_CLIMATE_ENABLED))

    @property
    def heat_mode(self) -> str:
        return self._heat_mode

    @property
    def cool_mode(self) -> str:
        return self._cool_mode

    @property
    def auto_heat(self) -> bool:
        return self._auto_heat

    @property
    def auto_cool(self) -> bool:
        return self._auto_cool

    @property
    def _client(self) -> DaikinWifiClient:
        return self.coordinator._client  # noqa: SLF001 — shared HTTP client

    def update_options(self, options: dict[str, Any]) -> None:
        self.options = dict(options)
        self._restart_listeners()

    async def async_setup(self) -> None:
        await self._async_load()
        self._restart_listeners()
        self._notify()
        # Re-apply last manual scene after reload (AUTO will re-evaluate itself).
        if self.enabled and not self._auto_heat and not self._auto_cool:
            if self._heat_mode != "off":
                self.hass.async_create_task(self.async_apply_heat_mode(self._heat_mode))
            elif self._cool_mode != "off":
                self.hass.async_create_task(self.async_apply_cool_mode(self._cool_mode))
        elif self.enabled and (self._auto_heat or self._auto_cool):
            self.hass.async_create_task(self.async_evaluate())

    async def async_shutdown(self) -> None:
        self._stop_listeners()
        await self._async_save()

    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_CLIMATE_UPDATED)

    def _restart_listeners(self) -> None:
        self._stop_listeners()
        if not self.enabled:
            return

        self._unsub_interval = async_track_time_interval(
            self.hass, self._async_on_interval, timedelta(seconds=60)
        )
        entities = [
            entity_id
            for entity_id in (
                self.options.get(CONF_SALON_TEMP_SENSOR),
                self.options.get(CONF_OUTDOOR_TEMP_SENSOR),
                self.options.get(CONF_PRESENCE_SENSOR),
                *list((self.options.get(CONF_OPENING_SENSORS) or {}).values()),
            )
            if entity_id
        ]
        if entities:
            self._unsub_states = async_track_state_change_event(
                self.hass, entities, self._async_on_state_event
            )

    def _stop_listeners(self) -> None:
        if self._unsub_interval:
            self._unsub_interval()
            self._unsub_interval = None
        if self._unsub_states:
            self._unsub_states()
            self._unsub_states = None

    @callback
    def _async_on_interval(self, _now: datetime) -> None:
        if self.enabled and (self._auto_heat or self._auto_cool):
            self.hass.async_create_task(self.async_evaluate())

    @callback
    def _async_on_state_event(self, _event: Any) -> None:
        if self.enabled and (self._auto_heat or self._auto_cool):
            self.hass.async_create_task(self.async_evaluate())

    async def _async_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        data = await self._store.async_load() or {}
        # Prefer stored runtime state; do not fall back to options defaults
        # (those are always "off" and would wipe a saved Confort on reload).
        if CONF_HEAT_MODE in data:
            heat = str(data.get(CONF_HEAT_MODE))
        else:
            heat = DEFAULT_HEAT_MODE
        if CONF_COOL_MODE in data:
            cool = str(data.get(CONF_COOL_MODE))
        else:
            cool = DEFAULT_COOL_MODE
        self._heat_mode = heat if heat in HEAT_MODES else DEFAULT_HEAT_MODE
        self._cool_mode = cool if cool in COOL_MODES else DEFAULT_COOL_MODE
        self._auto_heat = bool(data.get(CONF_AUTO_HEAT, DEFAULT_AUTO_HEAT))
        self._auto_cool = bool(data.get(CONF_AUTO_COOL, DEFAULT_AUTO_COOL))
        raw_openings = data.get("opening_since") or {}
        for key, iso in raw_openings.items():
            try:
                self._opening_since[key] = dt_util.parse_datetime(iso) or dt_util.utcnow()
            except (TypeError, ValueError):
                continue
        _LOGGER.debug(
            "Climate state loaded: heat=%s cool=%s auto_heat=%s auto_cool=%s",
            self._heat_mode,
            self._cool_mode,
            self._auto_heat,
            self._auto_cool,
        )

    async def _async_save(self) -> None:
        payload = {
            CONF_HEAT_MODE: self._heat_mode,
            CONF_COOL_MODE: self._cool_mode,
            CONF_AUTO_HEAT: self._auto_heat,
            CONF_AUTO_COOL: self._auto_cool,
            "opening_since": {
                key: value.isoformat() for key, value in self._opening_since.items()
            },
        }
        await self._store.async_save(payload)
        self._notify()
        if self._on_state_change:
            await self._on_state_change()

    async def async_set_heat_mode(self, mode: str, *, from_auto: bool = False) -> None:
        async with self._lock:
            mode = mode if mode in HEAT_MODES else DEFAULT_HEAT_MODE
            if not from_auto:
                self._eval_seq += 1
                self._auto_heat = False
            self._heat_mode = mode
            if mode != "off":
                # Heating scene wins: turn cooling off.
                self._cool_mode = "off"
                self._last_applied_cool = None
            await self._async_save()
            await self.async_apply_heat_mode(mode)

    async def async_set_cool_mode(self, mode: str, *, from_auto: bool = False) -> None:
        async with self._lock:
            mode = mode if mode in COOL_MODES else DEFAULT_COOL_MODE
            if not from_auto:
                self._eval_seq += 1
                self._auto_cool = False
            # DRY is always manual — leave AUTO cool off.
            if mode == "dry":
                self._auto_cool = False
            self._cool_mode = mode
            if mode != "off":
                self._heat_mode = "off"
                self._last_applied_heat = None
            await self._async_save()
            await self.async_apply_cool_mode(mode)

    async def async_set_auto_heat(self, enabled: bool) -> None:
        async with self._lock:
            self._auto_heat = bool(enabled)
            if enabled:
                self._auto_cool = False
            self._eval_seq += 1
            await self._async_save()
        if enabled:
            await self.async_evaluate()

    async def async_set_auto_cool(self, enabled: bool) -> None:
        async with self._lock:
            self._auto_cool = bool(enabled)
            if enabled:
                self._auto_heat = False
                if self._cool_mode == "dry":
                    self._cool_mode = "off"
            self._eval_seq += 1
            await self._async_save()
        if enabled:
            await self.async_evaluate()

    def _heat_presets(self) -> dict[str, dict[str, DeviceSetpoint]]:
        return presets_from_dict(self.options.get(CONF_HEAT_PRESETS), DEFAULT_HEAT_PRESETS)

    def _cool_presets(self) -> dict[str, dict[str, DeviceSetpoint]]:
        return presets_from_dict(self.options.get(CONF_COOL_PRESETS), DEFAULT_COOL_PRESETS)

    def _setpoint_for(
        self,
        presets: dict[str, dict[str, DeviceSetpoint]],
        mode: str,
        module: TrackedModule,
    ) -> DeviceSetpoint:
        devices = presets.get(mode) or {}
        # Prefer entry_id override from options UI, then host, then default key.
        for key in (module.entry_id, module.host):
            if key in devices:
                return devices[key]
        device_key = match_device_key(module.host, module.title)
        if device_key and device_key in devices:
            return devices[device_key]
        return DeviceSetpoint(power=False)

    def _opening_blocked(self, module: TrackedModule) -> bool:
        mapping: dict[str, str] = dict(self.options.get(CONF_OPENING_SENSORS) or {})
        entity_id = mapping.get(module.entry_id) or mapping.get(module.host)
        if not entity_id:
            device_key = match_device_key(module.host, module.title)
            if device_key:
                entity_id = mapping.get(device_key)
        if not entity_id:
            return False

        state = self.hass.states.get(entity_id)
        track_key = module.entry_id
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            self._opening_since.pop(track_key, None)
            return False

        is_open = state.state.casefold() in _OPEN_STATES
        delay = int(
            self.options.get(CONF_OPENING_DELAY_SECONDS, DEFAULT_OPENING_DELAY_SECONDS)
        )
        blocked, since = opening_is_blocking(
            is_open=is_open,
            open_since=self._opening_since.get(track_key),
            now=dt_util.utcnow(),
            delay_seconds=delay,
        )
        if since is None:
            self._opening_since.pop(track_key, None)
        else:
            self._opening_since[track_key] = since
        return blocked

    async def async_apply_heat_mode(self, mode: str | None = None) -> None:
        mode = mode or self._heat_mode
        if mode not in HEAT_MODES:
            return
        presets = self._heat_presets()
        modules = self.coordinator.discover_modules()
        _LOGGER.info("Applying heat mode %s to %s modules", mode, len(modules))
        for module in modules:
            if module.disabled:
                continue
            setpoint = self._setpoint_for(presets, mode, module)
            if mode != "off" and self._opening_blocked(module):
                setpoint = DeviceSetpoint(power=False)
            await self._async_apply_setpoint(module, setpoint)
        self._last_applied_heat = mode
        self._heat_mode = mode

    async def async_apply_cool_mode(self, mode: str | None = None) -> None:
        mode = mode or self._cool_mode
        if mode not in COOL_MODES:
            return
        presets = self._cool_presets()
        modules = self.coordinator.discover_modules()
        _LOGGER.info("Applying cool mode %s to %s modules", mode, len(modules))
        for module in modules:
            if module.disabled:
                continue
            setpoint = self._setpoint_for(presets, mode, module)
            if mode != "off" and mode != "dry" and self._opening_blocked(module):
                setpoint = DeviceSetpoint(power=False)
            await self._async_apply_setpoint(module, setpoint)
        self._last_applied_cool = mode
        self._cool_mode = mode

    async def _async_apply_setpoint(
        self, module: TrackedModule, setpoint: DeviceSetpoint
    ) -> None:
        try:
            await self._client.set_control_info(
                module.host,
                power=setpoint.power,
                mode=setpoint.mode if setpoint.power else None,
                temp=setpoint.temp if setpoint.power else None,
                fan_rate=setpoint.fan_rate if setpoint.power else None,
                fan_dir=setpoint.fan_dir if setpoint.power else None,
                creds=module.creds,
            )
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning(
                "Failed to set climate on %s (%s): %s",
                module.title,
                module.host,
                exc,
            )

    def _sensor_float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _presence_home(self) -> bool | None:
        entity_id = self.options.get(CONF_PRESENCE_SENSOR)
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return None
        value = state.state.casefold()
        if value in _PRESENCE_HOME:
            return True
        if value in {STATE_NOT_HOME, STATE_OFF, "away", "not_home", "false"}:
            return False
        # device_trackers / person: anything else treated as away
        return value == "home"

    def _is_night(self) -> bool:
        """Night scene window (local HA timezone), default 21:00–06:00."""
        return is_night_hour(
            dt_util.now().hour,
            night_start_hour=int(
                self.options.get(CONF_NIGHT_START_HOUR, DEFAULT_NIGHT_START_HOUR)
            ),
            night_end_hour=int(
                self.options.get(CONF_NIGHT_END_HOUR, DEFAULT_NIGHT_END_HOUR)
            ),
        )

    def _desired_heat_mode(self) -> str | None:
        """Return target heat mode, or None when AUTO heat should stay idle."""
        return desired_heat_mode(
            salon=self._sensor_float(self.options.get(CONF_SALON_TEMP_SENSOR)),
            outdoor=self._sensor_float(self.options.get(CONF_OUTDOOR_TEMP_SENSOR)),
            presence_home=self._presence_home(),
            is_night=self._is_night(),
            current_mode=self._heat_mode,
            heat_on_salon_below=float(
                self.options.get(CONF_HEAT_ON_SALON_BELOW, DEFAULT_HEAT_ON_SALON_BELOW)
            ),
            heat_on_outdoor_below=float(
                self.options.get(CONF_HEAT_ON_OUTDOOR_BELOW, DEFAULT_HEAT_ON_OUTDOOR_BELOW)
            ),
            heat_off_salon_above=float(
                self.options.get(CONF_HEAT_OFF_SALON_ABOVE, DEFAULT_HEAT_OFF_SALON_ABOVE)
            ),
            heat_off_outdoor_above=float(
                self.options.get(CONF_HEAT_OFF_OUTDOOR_ABOVE, DEFAULT_HEAT_OFF_OUTDOOR_ABOVE)
            ),
        )

    def _desired_cool_mode(self) -> str | None:
        return desired_cool_mode(
            salon=self._sensor_float(self.options.get(CONF_SALON_TEMP_SENSOR)),
            outdoor=self._sensor_float(self.options.get(CONF_OUTDOOR_TEMP_SENSOR)),
            presence_home=self._presence_home(),
            is_night=self._is_night(),
            current_mode=self._cool_mode,
            cool_on_salon_above=float(
                self.options.get(CONF_COOL_ON_SALON_ABOVE, DEFAULT_COOL_ON_SALON_ABOVE)
            ),
            cool_on_outdoor_above=float(
                self.options.get(CONF_COOL_ON_OUTDOOR_ABOVE, DEFAULT_COOL_ON_OUTDOOR_ABOVE)
            ),
            cool_off_outdoor_below=float(
                self.options.get(CONF_COOL_OFF_OUTDOOR_BELOW, DEFAULT_COOL_OFF_OUTDOOR_BELOW)
            ),
        )

    async def async_evaluate(self) -> None:
        """Run AUTO rules and re-apply openings overrides."""
        if not self.enabled:
            return

        seq = self._eval_seq
        async with self._lock:
            if seq != self._eval_seq:
                # A manual change happened while we were waiting — abort.
                return

            self._applying_auto = True
            try:
                if self._auto_heat:
                    desired = self._desired_heat_mode()
                    if desired is not None:
                        self._heat_mode = desired
                        if desired != "off":
                            self._cool_mode = "off"
                            self._last_applied_cool = None
                        await self._async_save()
                        await self.async_apply_heat_mode(desired)
                elif self._auto_cool:
                    if self._cool_mode == "dry":
                        return
                    desired = self._desired_cool_mode()
                    if desired is not None:
                        self._cool_mode = desired
                        if desired != "off":
                            self._heat_mode = "off"
                            self._last_applied_heat = None
                        await self._async_save()
                        await self.async_apply_cool_mode(desired)
                else:
                    # Manual mode: still honour opening cut-off by re-applying.
                    if self._heat_mode != "off":
                        await self.async_apply_heat_mode(self._heat_mode)
                    elif self._cool_mode != "off":
                        await self.async_apply_cool_mode(self._cool_mode)
            finally:
                self._applying_auto = False
