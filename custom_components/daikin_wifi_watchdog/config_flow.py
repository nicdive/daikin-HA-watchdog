"""Config flow for Daikin WiFi Watchdog."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .climate_defaults import (
    COOL_MODE_LABELS,
    COOL_MODES,
    DEFAULT_COOL_OFF_OUTDOOR_BELOW,
    DEFAULT_COOL_ON_OUTDOOR_ABOVE,
    DEFAULT_COOL_ON_SALON_ABOVE,
    DEFAULT_HEAT_OFF_OUTDOOR_ABOVE,
    DEFAULT_HEAT_OFF_SALON_ABOVE,
    DEFAULT_HEAT_ON_OUTDOOR_BELOW,
    DEFAULT_HEAT_ON_SALON_BELOW,
    DEFAULT_OPENING_DELAY_SECONDS,
    DEVICE_HOSTS,
    FAN_DIR_OPTIONS,
    FAN_RATE_OPTIONS,
    HEAT_MODE_LABELS,
    HEAT_MODES,
    match_device_key,
    serialize_default_cool_presets,
    serialize_default_heat_presets,
)
from .helpers import daikin_entry_display_name
from .const import (
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_CLIMATE_ENABLED,
    CONF_CONFIGURE_CLIMATE,
    CONF_CONFIGURE_COOL_PRESETS,
    CONF_CONFIGURE_HARD_SWITCHES,
    CONF_CONFIGURE_HEAT_PRESETS,
    CONF_COOL_OFF_OUTDOOR_BELOW,
    CONF_COOL_ON_OUTDOOR_ABOVE,
    CONF_COOL_ON_SALON_ABOVE,
    CONF_COOL_PRESETS,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_OFF_SECONDS,
    CONF_HARD_REBOOT_SWITCH,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HEAT_OFF_OUTDOOR_ABOVE,
    CONF_HEAT_OFF_SALON_ABOVE,
    CONF_HEAT_ON_OUTDOOR_BELOW,
    CONF_HEAT_ON_SALON_BELOW,
    CONF_HEAT_PRESETS,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_NIGHT_END_HOUR,
    CONF_NIGHT_START_HOUR,
    CONF_OPENING_DELAY_SECONDS,
    CONF_OPENING_SENSORS,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_PRESENCE_SENSOR,
    CONF_REBOOT_COOLDOWN,
    CONF_RELOAD_DAIKIN,
    CONF_SALON_TEMP_SENSOR,
    CONF_SUN_ENTITY,
    CONF_WATCHDOG_ENABLED,
    DAIKIN_DOMAIN,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_CLIMATE_ENABLED,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HARD_REBOOT_OFF_SECONDS,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_NIGHT_END_HOUR,
    DEFAULT_NIGHT_START_HOUR,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_REBOOT_COOLDOWN,
    DEFAULT_RELOAD_DAIKIN,
    DEFAULT_SUN_ENTITY,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
)

_CLIMATE_OPTION_KEYS = (
    CONF_CLIMATE_ENABLED,
    CONF_SALON_TEMP_SENSOR,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_PRESENCE_SENSOR,
    CONF_SUN_ENTITY,
    CONF_NIGHT_START_HOUR,
    CONF_NIGHT_END_HOUR,
    CONF_OPENING_SENSORS,
    CONF_OPENING_DELAY_SECONDS,
    CONF_HEAT_PRESETS,
    CONF_COOL_PRESETS,
    CONF_HEAT_ON_SALON_BELOW,
    CONF_HEAT_ON_OUTDOOR_BELOW,
    CONF_HEAT_OFF_SALON_ABOVE,
    CONF_HEAT_OFF_OUTDOOR_ABOVE,
    CONF_COOL_ON_SALON_ABOVE,
    CONF_COOL_ON_OUTDOOR_ABOVE,
    CONF_COOL_OFF_OUTDOOR_BELOW,
)


def _guess_mobile_notify(hass: HomeAssistant) -> str:
    """Best-effort match for a Companion notify target."""
    services = hass.services.async_services().get("notify", {})
    mobile: list[str] = []
    preferred: list[str] = []
    for name in services:
        lower = name.lower()
        if not lower.startswith("mobile_app_"):
            continue
        entity = f"notify.{name}"
        mobile.append(entity)
        if "iphone" in lower:
            preferred.append(entity)
    if preferred:
        return preferred[0]
    return mobile[0] if mobile else ""


def _notify_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="notify", multiple=False)
    )


def _switch_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="switch", multiple=False)
    )


def _sensor_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="sensor",
            device_class="temperature",
            multiple=False,
        )
    )


def _binary_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain="binary_sensor", multiple=False)
    )


def _presence_selector() -> selector.EntitySelector:
    return selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain=["person", "device_tracker", "binary_sensor", "input_boolean"],
            multiple=False,
        )
    )


class DaikinWifiWatchdogConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-instance config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        daikin_entries = self.hass.config_entries.async_entries(DAIKIN_DOMAIN)
        if user_input is not None:
            notify = user_input.get(CONF_NOTIFY_SERVICE) or _guess_mobile_notify(self.hass)
            return self.async_create_entry(
                title="Daikin WiFi Watchdog",
                data={},
                options={
                    CONF_CHECK_INTERVAL: user_input.get(
                        CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL
                    ),
                    CONF_FAILURES_BEFORE_REBOOT: user_input.get(
                        CONF_FAILURES_BEFORE_REBOOT, DEFAULT_FAILURES_BEFORE_REBOOT
                    ),
                    CONF_AUTO_REBOOT: user_input.get(CONF_AUTO_REBOOT, DEFAULT_AUTO_REBOOT),
                    CONF_REBOOT_COOLDOWN: DEFAULT_REBOOT_COOLDOWN,
                    CONF_MAX_SOFT_REBOOTS_PER_DAY: DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
                    CONF_HTTP_TIMEOUT: DEFAULT_HTTP_TIMEOUT,
                    CONF_HARD_REBOOT_SWITCHES: {},
                    CONF_HARD_REBOOT_OFF_SECONDS: DEFAULT_HARD_REBOOT_OFF_SECONDS,
                    CONF_WATCHDOG_ENABLED: DEFAULT_WATCHDOG_ENABLED,
                    CONF_NOTIFICATIONS_ENABLED: user_input.get(
                        CONF_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED
                    ),
                    CONF_NOTIFY_SERVICE: notify,
                    CONF_RELOAD_DAIKIN: DEFAULT_RELOAD_DAIKIN,
                    CONF_CLIMATE_ENABLED: DEFAULT_CLIMATE_ENABLED,
                    CONF_HEAT_PRESETS: serialize_default_heat_presets(),
                    CONF_COOL_PRESETS: serialize_default_cool_presets(),
                    CONF_OPENING_SENSORS: {},
                    CONF_OPENING_DELAY_SECONDS: DEFAULT_OPENING_DELAY_SECONDS,
                    CONF_SUN_ENTITY: DEFAULT_SUN_ENTITY,
                    CONF_NIGHT_START_HOUR: DEFAULT_NIGHT_START_HOUR,
                    CONF_NIGHT_END_HOUR: DEFAULT_NIGHT_END_HOUR,
                    CONF_HEAT_ON_SALON_BELOW: DEFAULT_HEAT_ON_SALON_BELOW,
                    CONF_HEAT_ON_OUTDOOR_BELOW: DEFAULT_HEAT_ON_OUTDOOR_BELOW,
                    CONF_HEAT_OFF_SALON_ABOVE: DEFAULT_HEAT_OFF_SALON_ABOVE,
                    CONF_HEAT_OFF_OUTDOOR_ABOVE: DEFAULT_HEAT_OFF_OUTDOOR_ABOVE,
                    CONF_COOL_ON_SALON_ABOVE: DEFAULT_COOL_ON_SALON_ABOVE,
                    CONF_COOL_ON_OUTDOOR_ABOVE: DEFAULT_COOL_ON_OUTDOOR_ABOVE,
                    CONF_COOL_OFF_OUTDOOR_BELOW: DEFAULT_COOL_OFF_OUTDOOR_BELOW,
                },
            )

        guessed = _guess_mobile_notify(self.hass)
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_CHECK_INTERVAL, default=DEFAULT_CHECK_INTERVAL
            ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            vol.Required(
                CONF_FAILURES_BEFORE_REBOOT,
                default=DEFAULT_FAILURES_BEFORE_REBOOT,
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Required(CONF_AUTO_REBOOT, default=DEFAULT_AUTO_REBOOT): bool,
            vol.Required(
                CONF_NOTIFICATIONS_ENABLED, default=DEFAULT_NOTIFICATIONS_ENABLED
            ): bool,
        }
        if guessed:
            schema[vol.Optional(CONF_NOTIFY_SERVICE, default=guessed)] = _notify_selector()
        else:
            schema[vol.Optional(CONF_NOTIFY_SERVICE)] = _notify_selector()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "daikin_count": str(len(daikin_entries)),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return DaikinWifiWatchdogOptionsFlow(config_entry)


class DaikinWifiWatchdogOptionsFlow(config_entries.OptionsFlow):
    """Options flow: watchdog + climate scenes / AUTO rules."""

    def __init__(self, config_entry: config_entries.ConfigEntry | None = None) -> None:
        if config_entry is not None:
            self._config_entry = config_entry
        self._pending: dict[str, Any] = {}
        self._daikin_queue: list[config_entries.ConfigEntry] = []
        self._hard_map: dict[str, str] = {}
        self._opening_map: dict[str, str] = {}
        self._index = 0
        self._preset_modes: list[str] = []
        self._preset_devices: list[tuple[str, str, str | None]] = []
        self._preset_kind: str | None = None
        self._preset_mode_index = 0
        self._preset_device_index = 0
        self._want_heat_presets = False
        self._want_cool_presets = False

    def _entry(self) -> config_entries.ConfigEntry:
        return getattr(self, "config_entry", None) or self._config_entry

    def _current_options(self) -> dict[str, Any]:
        return dict(self._entry().options or {})

    def _copy_climate_options(self, current: dict[str, Any]) -> None:
        for key in _CLIMATE_OPTION_KEYS:
            if key in current:
                self._pending[key] = current[key]
        self._pending.setdefault(CONF_CLIMATE_ENABLED, DEFAULT_CLIMATE_ENABLED)
        self._pending.setdefault(CONF_HEAT_PRESETS, serialize_default_heat_presets())
        self._pending.setdefault(CONF_COOL_PRESETS, serialize_default_cool_presets())
        self._pending.setdefault(CONF_OPENING_SENSORS, {})
        self._pending.setdefault(CONF_OPENING_DELAY_SECONDS, DEFAULT_OPENING_DELAY_SECONDS)
        self._pending.setdefault(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY)
        self._pending.setdefault(CONF_NIGHT_START_HOUR, DEFAULT_NIGHT_START_HOUR)
        self._pending.setdefault(CONF_NIGHT_END_HOUR, DEFAULT_NIGHT_END_HOUR)

    def _finish(self) -> FlowResult:
        return self.async_create_entry(title="", data=self._pending)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self._current_options()
        daikin_entries = [
            entry
            for entry in self.hass.config_entries.async_entries(DAIKIN_DOMAIN)
            if entry.source != config_entries.SOURCE_IGNORE
        ]

        if user_input is not None:
            self._pending = {
                CONF_CHECK_INTERVAL: user_input[CONF_CHECK_INTERVAL],
                CONF_FAILURES_BEFORE_REBOOT: user_input[CONF_FAILURES_BEFORE_REBOOT],
                CONF_AUTO_REBOOT: user_input[CONF_AUTO_REBOOT],
                CONF_REBOOT_COOLDOWN: user_input[CONF_REBOOT_COOLDOWN],
                CONF_MAX_SOFT_REBOOTS_PER_DAY: user_input[CONF_MAX_SOFT_REBOOTS_PER_DAY],
                CONF_HTTP_TIMEOUT: user_input[CONF_HTTP_TIMEOUT],
                CONF_HARD_REBOOT_OFF_SECONDS: user_input[CONF_HARD_REBOOT_OFF_SECONDS],
                CONF_RELOAD_DAIKIN: user_input[CONF_RELOAD_DAIKIN],
                CONF_WATCHDOG_ENABLED: current.get(
                    CONF_WATCHDOG_ENABLED, DEFAULT_WATCHDOG_ENABLED
                ),
                CONF_NOTIFICATIONS_ENABLED: current.get(
                    CONF_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED
                ),
                CONF_NOTIFY_SERVICE: user_input.get(CONF_NOTIFY_SERVICE)
                or current.get(CONF_NOTIFY_SERVICE)
                or "",
            }
            self._copy_climate_options(current)
            existing_map = dict(current.get(CONF_HARD_REBOOT_SWITCHES) or {})
            configure_hard = bool(user_input.get(CONF_CONFIGURE_HARD_SWITCHES))
            configure_climate = bool(user_input.get(CONF_CONFIGURE_CLIMATE))
            if configure_hard and daikin_entries:
                self._daikin_queue = daikin_entries
                self._hard_map = {}
                self._index = 0
                self._pending["_after_hard"] = "climate" if configure_climate else "done"
                return await self.async_step_hard_switch()
            self._pending[CONF_HARD_REBOOT_SWITCHES] = existing_map
            if configure_climate:
                return await self.async_step_climate()
            return self._finish()

        notify_default = current.get(CONF_NOTIFY_SERVICE) or _guess_mobile_notify(self.hass)
        has_hard = bool(current.get(CONF_HARD_REBOOT_SWITCHES))
        has_climate = bool(
            current.get(CONF_SALON_TEMP_SENSOR)
            or current.get(CONF_OUTDOOR_TEMP_SENSOR)
            or current.get(CONF_OPENING_SENSORS)
        )
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_CHECK_INTERVAL,
                default=current.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
            vol.Required(
                CONF_FAILURES_BEFORE_REBOOT,
                default=current.get(
                    CONF_FAILURES_BEFORE_REBOOT, DEFAULT_FAILURES_BEFORE_REBOOT
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=20)),
            vol.Required(
                CONF_AUTO_REBOOT,
                default=current.get(CONF_AUTO_REBOOT, DEFAULT_AUTO_REBOOT),
            ): bool,
            vol.Required(
                CONF_REBOOT_COOLDOWN,
                default=current.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN),
            ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
            vol.Required(
                CONF_MAX_SOFT_REBOOTS_PER_DAY,
                default=current.get(
                    CONF_MAX_SOFT_REBOOTS_PER_DAY, DEFAULT_MAX_SOFT_REBOOTS_PER_DAY
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=50)),
            vol.Required(
                CONF_HTTP_TIMEOUT,
                default=current.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT),
            ): vol.All(vol.Coerce(int), vol.Range(min=2, max=60)),
            vol.Required(
                CONF_HARD_REBOOT_OFF_SECONDS,
                default=current.get(
                    CONF_HARD_REBOOT_OFF_SECONDS, DEFAULT_HARD_REBOOT_OFF_SECONDS
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
            vol.Required(
                CONF_RELOAD_DAIKIN,
                default=current.get(CONF_RELOAD_DAIKIN, DEFAULT_RELOAD_DAIKIN),
            ): bool,
        }
        if notify_default:
            schema[vol.Optional(CONF_NOTIFY_SERVICE, default=notify_default)] = (
                _notify_selector()
            )
        else:
            schema[vol.Optional(CONF_NOTIFY_SERVICE)] = _notify_selector()
        schema[vol.Optional(CONF_CONFIGURE_HARD_SWITCHES, default=has_hard)] = bool
        schema[vol.Optional(CONF_CONFIGURE_CLIMATE, default=has_climate)] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "daikin_count": str(len(daikin_entries)),
            },
        )

    async def async_step_hard_switch(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._daikin_queue[self._index]
        current_map = self._current_options().get(CONF_HARD_REBOOT_SWITCHES) or {}
        if user_input is not None:
            value = user_input.get(CONF_HARD_REBOOT_SWITCH)
            if value:
                self._hard_map[entry.entry_id] = value
            self._index += 1
            if self._index < len(self._daikin_queue):
                return await self.async_step_hard_switch()
            self._pending[CONF_HARD_REBOOT_SWITCHES] = self._hard_map
            after = self._pending.pop("_after_hard", "done")
            if after == "climate":
                return await self.async_step_climate()
            return self._finish()

        default = current_map.get(entry.entry_id)
        schema: dict[Any, Any]
        if default:
            schema = {
                vol.Optional(CONF_HARD_REBOOT_SWITCH, default=default): _switch_selector()
            }
        else:
            schema = {vol.Optional(CONF_HARD_REBOOT_SWITCH): _switch_selector()}
        return self.async_show_form(
            step_id="hard_switch",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "name": entry.title or entry.entry_id,
                "host": str(entry.data.get(CONF_HOST) or ""),
            },
        )

    async def async_step_climate(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        current = self._current_options()
        if user_input is not None:
            self._pending[CONF_CLIMATE_ENABLED] = user_input[CONF_CLIMATE_ENABLED]
            self._pending[CONF_SALON_TEMP_SENSOR] = (
                user_input.get(CONF_SALON_TEMP_SENSOR) or ""
            )
            self._pending[CONF_OUTDOOR_TEMP_SENSOR] = (
                user_input.get(CONF_OUTDOOR_TEMP_SENSOR) or ""
            )
            self._pending[CONF_PRESENCE_SENSOR] = (
                user_input.get(CONF_PRESENCE_SENSOR) or ""
            )
            self._pending[CONF_SUN_ENTITY] = (
                user_input.get(CONF_SUN_ENTITY)
                or current.get(CONF_SUN_ENTITY)
                or DEFAULT_SUN_ENTITY
            )
            self._pending[CONF_NIGHT_START_HOUR] = int(
                user_input[CONF_NIGHT_START_HOUR]
            )
            self._pending[CONF_NIGHT_END_HOUR] = int(user_input[CONF_NIGHT_END_HOUR])
            self._pending[CONF_OPENING_DELAY_SECONDS] = user_input[
                CONF_OPENING_DELAY_SECONDS
            ]
            self._pending[CONF_HEAT_ON_SALON_BELOW] = user_input[CONF_HEAT_ON_SALON_BELOW]
            self._pending[CONF_HEAT_ON_OUTDOOR_BELOW] = user_input[
                CONF_HEAT_ON_OUTDOOR_BELOW
            ]
            self._pending[CONF_HEAT_OFF_SALON_ABOVE] = user_input[
                CONF_HEAT_OFF_SALON_ABOVE
            ]
            self._pending[CONF_HEAT_OFF_OUTDOOR_ABOVE] = user_input[
                CONF_HEAT_OFF_OUTDOOR_ABOVE
            ]
            self._pending[CONF_COOL_ON_SALON_ABOVE] = user_input[CONF_COOL_ON_SALON_ABOVE]
            self._pending[CONF_COOL_ON_OUTDOOR_ABOVE] = user_input[
                CONF_COOL_ON_OUTDOOR_ABOVE
            ]
            self._pending[CONF_COOL_OFF_OUTDOOR_BELOW] = user_input[
                CONF_COOL_OFF_OUTDOOR_BELOW
            ]
            self._want_heat_presets = bool(user_input.get(CONF_CONFIGURE_HEAT_PRESETS))
            self._want_cool_presets = bool(user_input.get(CONF_CONFIGURE_COOL_PRESETS))

            daikin_entries = [
                entry
                for entry in self.hass.config_entries.async_entries(DAIKIN_DOMAIN)
                if entry.source != config_entries.SOURCE_IGNORE
            ]
            if daikin_entries:
                self._daikin_queue = daikin_entries
                self._opening_map = {}
                self._index = 0
                return await self.async_step_opening()
            return await self._after_openings()

        def _opt(key: str, default: Any = "") -> Any:
            return current.get(key) or self._pending.get(key) or default

        schema: dict[Any, Any] = {
            vol.Required(
                CONF_CLIMATE_ENABLED,
                default=bool(_opt(CONF_CLIMATE_ENABLED, DEFAULT_CLIMATE_ENABLED)),
            ): bool,
        }
        salon = _opt(CONF_SALON_TEMP_SENSOR)
        outdoor = _opt(CONF_OUTDOOR_TEMP_SENSOR)
        presence = _opt(CONF_PRESENCE_SENSOR)
        if salon:
            schema[vol.Optional(CONF_SALON_TEMP_SENSOR, default=salon)] = _sensor_selector()
        else:
            schema[vol.Optional(CONF_SALON_TEMP_SENSOR)] = _sensor_selector()
        if outdoor:
            schema[vol.Optional(CONF_OUTDOOR_TEMP_SENSOR, default=outdoor)] = (
                _sensor_selector()
            )
        else:
            schema[vol.Optional(CONF_OUTDOOR_TEMP_SENSOR)] = _sensor_selector()
        if presence:
            schema[vol.Optional(CONF_PRESENCE_SENSOR, default=presence)] = (
                _presence_selector()
            )
        else:
            schema[vol.Optional(CONF_PRESENCE_SENSOR)] = _presence_selector()
        schema[
            vol.Required(
                CONF_NIGHT_START_HOUR,
                default=int(_opt(CONF_NIGHT_START_HOUR, DEFAULT_NIGHT_START_HOUR)),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=23))
        schema[
            vol.Required(
                CONF_NIGHT_END_HOUR,
                default=int(_opt(CONF_NIGHT_END_HOUR, DEFAULT_NIGHT_END_HOUR)),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=23))
        schema[
            vol.Required(
                CONF_OPENING_DELAY_SECONDS,
                default=int(
                    _opt(CONF_OPENING_DELAY_SECONDS, DEFAULT_OPENING_DELAY_SECONDS)
                ),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=0, max=3600))
        schema[
            vol.Required(
                CONF_HEAT_ON_SALON_BELOW,
                default=float(_opt(CONF_HEAT_ON_SALON_BELOW, DEFAULT_HEAT_ON_SALON_BELOW)),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                CONF_HEAT_ON_OUTDOOR_BELOW,
                default=float(
                    _opt(CONF_HEAT_ON_OUTDOOR_BELOW, DEFAULT_HEAT_ON_OUTDOOR_BELOW)
                ),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                CONF_HEAT_OFF_SALON_ABOVE,
                default=float(
                    _opt(CONF_HEAT_OFF_SALON_ABOVE, DEFAULT_HEAT_OFF_SALON_ABOVE)
                ),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                CONF_HEAT_OFF_OUTDOOR_ABOVE,
                default=float(
                    _opt(CONF_HEAT_OFF_OUTDOOR_ABOVE, DEFAULT_HEAT_OFF_OUTDOOR_ABOVE)
                ),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                CONF_COOL_ON_SALON_ABOVE,
                default=float(_opt(CONF_COOL_ON_SALON_ABOVE, DEFAULT_COOL_ON_SALON_ABOVE)),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                CONF_COOL_ON_OUTDOOR_ABOVE,
                default=float(
                    _opt(CONF_COOL_ON_OUTDOOR_ABOVE, DEFAULT_COOL_ON_OUTDOOR_ABOVE)
                ),
            )
        ] = vol.Coerce(float)
        schema[
            vol.Required(
                CONF_COOL_OFF_OUTDOOR_BELOW,
                default=float(
                    _opt(CONF_COOL_OFF_OUTDOOR_BELOW, DEFAULT_COOL_OFF_OUTDOOR_BELOW)
                ),
            )
        ] = vol.Coerce(float)
        schema[vol.Optional(CONF_CONFIGURE_HEAT_PRESETS, default=False)] = bool
        schema[vol.Optional(CONF_CONFIGURE_COOL_PRESETS, default=False)] = bool

        return self.async_show_form(step_id="climate", data_schema=vol.Schema(schema))

    async def async_step_opening(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self._daikin_queue[self._index]
        current_map = dict(
            self._pending.get(CONF_OPENING_SENSORS)
            or self._current_options().get(CONF_OPENING_SENSORS)
            or {}
        )
        if user_input is not None:
            value = user_input.get("opening_sensor")
            if value:
                self._opening_map[entry.entry_id] = value
            self._index += 1
            if self._index < len(self._daikin_queue):
                return await self.async_step_opening()
            self._pending[CONF_OPENING_SENSORS] = self._opening_map
            return await self._after_openings()

        default = current_map.get(entry.entry_id)
        schema: dict[Any, Any]
        if default:
            schema = {vol.Optional("opening_sensor", default=default): _binary_selector()}
        else:
            schema = {vol.Optional("opening_sensor"): _binary_selector()}
        return self.async_show_form(
            step_id="opening",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "name": daikin_entry_display_name(self.hass, entry),
                "host": str(entry.data.get(CONF_HOST) or ""),
            },
        )

    async def _after_openings(self) -> FlowResult:
        if self._want_heat_presets:
            self._preset_kind = "heat"
            self._preset_modes = [mode for mode in HEAT_MODES if mode != "off"]
            self._preset_devices = self._devices_for_presets()
            self._preset_mode_index = 0
            self._preset_device_index = 0
            if self._preset_devices:
                return await self.async_step_heat_preset()
        if self._want_cool_presets:
            return await self._start_cool_presets()
        return self._finish()

    async def _start_cool_presets(self) -> FlowResult:
        self._preset_kind = "cool"
        self._preset_modes = [mode for mode in COOL_MODES if mode != "off"]
        self._preset_devices = self._devices_for_presets()
        self._preset_mode_index = 0
        self._preset_device_index = 0
        if not self._preset_devices:
            return self._finish()
        return await self.async_step_cool_preset()

    def _devices_for_presets(self) -> list[tuple[str, str, str | None]]:
        """Return (storage_key, display_name, host) for each Daikin unit."""
        entries = [
            entry
            for entry in self.hass.config_entries.async_entries(DAIKIN_DOMAIN)
            if entry.source != config_entries.SOURCE_IGNORE
        ]
        if entries:
            return [
                (
                    entry.entry_id,
                    daikin_entry_display_name(self.hass, entry),
                    str(entry.data.get(CONF_HOST) or "") or None,
                )
                for entry in entries
            ]
        return [(key, key.replace("_", " ").title(), host) for key, host in DEVICE_HOSTS.items()]

    def _lookup_existing_setpoint(
        self,
        mode_presets: dict[str, Any],
        storage_key: str,
        host: str | None,
        title: str,
    ) -> dict[str, Any]:
        if storage_key in mode_presets and isinstance(mode_presets[storage_key], dict):
            return dict(mode_presets[storage_key])
        if host and host in mode_presets and isinstance(mode_presets[host], dict):
            return dict(mode_presets[host])
        device_key = match_device_key(host, title)
        if device_key and device_key in mode_presets and isinstance(
            mode_presets[device_key], dict
        ):
            return dict(mode_presets[device_key])
        return {}

    def _fan_selector(self, default: str) -> selector.SelectSelector:
        options = [
            {"value": "A", "label": "Auto"},
            {"value": "B", "label": "Silence"},
            {"value": "3", "label": "Débit 1"},
            {"value": "4", "label": "Débit 2"},
            {"value": "5", "label": "Débit 3"},
            {"value": "6", "label": "Débit 4"},
            {"value": "7", "label": "Débit 5"},
        ]
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    def _oscillation_selector(self) -> selector.SelectSelector:
        options = [
            {"value": "0", "label": "Arrêt (pas d'oscillation)"},
            {"value": "1", "label": "Oscillation verticale"},
            {"value": "2", "label": "Oscillation horizontale"},
            {"value": "3", "label": "Oscillation verticale + horizontale"},
        ]
        return selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=options,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

    def _advance_preset(self) -> str | None:
        """Advance device/mode indexes. Return next step id or None when done."""
        self._preset_device_index += 1
        if self._preset_device_index < len(self._preset_devices):
            return "same"
        self._preset_device_index = 0
        self._preset_mode_index += 1
        if self._preset_mode_index < len(self._preset_modes):
            return "same"
        return None

    async def async_step_heat_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        mode = self._preset_modes[self._preset_mode_index]
        storage_key, title, host = self._preset_devices[self._preset_device_index]
        presets = dict(
            self._pending.get(CONF_HEAT_PRESETS) or serialize_default_heat_presets()
        )
        mode_presets = dict(presets.get(mode) or {})
        existing = self._lookup_existing_setpoint(mode_presets, storage_key, host, title)

        if user_input is not None:
            enabled = bool(user_input.get("power", False))
            fan_rate = str(user_input.get("fan_rate") or "A")
            if fan_rate not in FAN_RATE_OPTIONS:
                fan_rate = "A"
            fan_dir = str(user_input.get("oscillation") or "3")
            if fan_dir not in FAN_DIR_OPTIONS:
                fan_dir = "3"
            if not enabled:
                mode_presets[storage_key] = {
                    "power": False,
                    "temp": None,
                    "mode": "4",
                    "fan_rate": "A",
                    "fan_dir": "3",
                }
            else:
                mode_presets[storage_key] = {
                    "power": True,
                    "temp": float(user_input.get("temperature") or 18.0),
                    "mode": "4",
                    "fan_rate": fan_rate,
                    "fan_dir": fan_dir,
                }
            presets[mode] = mode_presets
            self._pending[CONF_HEAT_PRESETS] = presets
            nxt = self._advance_preset()
            if nxt == "same":
                return await self.async_step_heat_preset()
            if self._want_cool_presets:
                return await self._start_cool_presets()
            return self._finish()

        power = bool(existing.get("power", False))
        temp = existing.get("temp")
        fan_rate = str(existing.get("fan_rate") or "A")
        if fan_rate not in FAN_RATE_OPTIONS:
            fan_rate = "A"
        fan_dir = str(existing.get("fan_dir") or "3")
        if fan_dir not in FAN_DIR_OPTIONS:
            fan_dir = "3"

        schema: dict[Any, Any] = {
            vol.Required("power", default=power): bool,
            vol.Required(
                "temperature",
                default=float(temp) if temp is not None else 18.0,
            ): vol.All(vol.Coerce(float), vol.Range(min=10, max=32)),
            vol.Required("fan_rate", default=fan_rate): self._fan_selector(fan_rate),
            vol.Required("oscillation", default=fan_dir): self._oscillation_selector(),
        }
        return self.async_show_form(
            step_id="heat_preset",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "mode": HEAT_MODE_LABELS.get(mode, mode),
                "name": title,
                "host": host or "",
            },
        )

    async def async_step_cool_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        mode = self._preset_modes[self._preset_mode_index]
        storage_key, title, host = self._preset_devices[self._preset_device_index]
        presets = dict(
            self._pending.get(CONF_COOL_PRESETS) or serialize_default_cool_presets()
        )
        mode_presets = dict(presets.get(mode) or {})
        existing = self._lookup_existing_setpoint(mode_presets, storage_key, host, title)

        if user_input is not None:
            enabled = bool(user_input.get("power", False))
            fan_rate = str(user_input.get("fan_rate") or "A")
            if fan_rate not in FAN_RATE_OPTIONS:
                fan_rate = "A"
            fan_dir = str(user_input.get("oscillation") or "3")
            if fan_dir not in FAN_DIR_OPTIONS:
                fan_dir = "3"
            if mode == "dry":
                mode_presets[storage_key] = {
                    "power": enabled,
                    "temp": None,
                    "mode": "2",
                    "fan_rate": fan_rate if enabled else "A",
                    "fan_dir": fan_dir if enabled else "3",
                }
            elif not enabled:
                mode_presets[storage_key] = {
                    "power": False,
                    "temp": None,
                    "mode": "3",
                    "fan_rate": "A",
                    "fan_dir": "3",
                }
            else:
                mode_presets[storage_key] = {
                    "power": True,
                    "temp": float(user_input.get("temperature") or 27.0),
                    "mode": "3",
                    "fan_rate": fan_rate,
                    "fan_dir": fan_dir,
                }
            presets[mode] = mode_presets
            self._pending[CONF_COOL_PRESETS] = presets
            nxt = self._advance_preset()
            if nxt == "same":
                return await self.async_step_cool_preset()
            return self._finish()

        power = bool(existing.get("power", False))
        temp = existing.get("temp")
        fan_rate = str(existing.get("fan_rate") or "A")
        if fan_rate not in FAN_RATE_OPTIONS:
            fan_rate = "A"
        fan_dir = str(existing.get("fan_dir") or "3")
        if fan_dir not in FAN_DIR_OPTIONS:
            fan_dir = "3"

        schema: dict[Any, Any] = {
            vol.Required("power", default=power): bool,
        }
        if mode != "dry":
            schema[
                vol.Required(
                    "temperature",
                    default=float(temp) if temp is not None else 27.0,
                )
            ] = vol.All(vol.Coerce(float), vol.Range(min=18, max=32))
        schema[vol.Required("fan_rate", default=fan_rate)] = self._fan_selector(fan_rate)
        schema[vol.Required("oscillation", default=fan_dir)] = self._oscillation_selector()

        return self.async_show_form(
            step_id="cool_preset",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "mode": COOL_MODE_LABELS.get(mode, mode),
                "name": title,
                "host": host or "",
            },
        )
