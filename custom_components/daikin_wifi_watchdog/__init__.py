"""Daikin WiFi Watchdog — monitors official Daikin AC integration modules."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect

try:
    from homeassistant.config_entries import SIGNAL_CONFIG_ENTRY_CHANGED
except ImportError:  # pragma: no cover - older HA
    SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"

from .climate_defaults import (
    DEFAULT_COOL_OFF_OUTDOOR_BELOW,
    DEFAULT_COOL_ON_OUTDOOR_ABOVE,
    DEFAULT_COOL_ON_SALON_ABOVE,
    DEFAULT_HEAT_OFF_OUTDOOR_ABOVE,
    DEFAULT_HEAT_OFF_SALON_ABOVE,
    DEFAULT_HEAT_ON_OUTDOOR_BELOW,
    DEFAULT_HEAT_ON_SALON_BELOW,
    DEFAULT_OPENING_DELAY_SECONDS,
    serialize_default_cool_presets,
    serialize_default_heat_presets,
)
from .climate_manager import ClimateManager
from .preset_editor import PresetEditor
from .const import (
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_CLIMATE_ENABLED,
    CONF_COOL_MODE,
    CONF_COOL_OFF_OUTDOOR_BELOW,
    CONF_COOL_ON_OUTDOOR_ABOVE,
    CONF_COOL_ON_SALON_ABOVE,
    CONF_COOL_PRESETS,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_OFF_SECONDS,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HEAT_MODE,
    CONF_HEAT_OFF_OUTDOOR_ABOVE,
    CONF_HEAT_OFF_SALON_ABOVE,
    CONF_HEAT_ON_OUTDOOR_BELOW,
    CONF_HEAT_ON_SALON_BELOW,
    CONF_HEAT_PRESETS,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_OPENING_DELAY_SECONDS,
    CONF_OPENING_SENSORS,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_PRESENCE_SENSOR,
    CONF_REBOOT_COOLDOWN,
    CONF_RELOAD_DAIKIN,
    CONF_SALON_TEMP_SENSOR,
    CONF_NIGHT_END_HOUR,
    CONF_NIGHT_START_HOUR,
    CONF_SUN_ENTITY,
    CONF_WATCHDOG_ENABLED,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_CLIMATE_ENABLED,
    DEFAULT_COOL_MODE,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HARD_REBOOT_OFF_SECONDS,
    DEFAULT_HEAT_MODE,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_REBOOT_COOLDOWN,
    DEFAULT_RELOAD_DAIKIN,
    DEFAULT_NIGHT_END_HOUR,
    DEFAULT_NIGHT_START_HOUR,
    DEFAULT_SUN_ENTITY,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
    PLATFORMS,
    SERVICE_APPLY_COOL_MODE,
    SERVICE_APPLY_HEAT_MODE,
    SERVICE_CHECK_NOW,
    SERVICE_CLIMATE_EVALUATE,
    SERVICE_HARD_REBOOT,
    SERVICE_REBOOT,
)
from .coordinator import DaikinWatchdogCoordinator
from .entity_cleanup import async_cleanup_stale_entities
from .helpers import integration_version

REBOOT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional(CONF_HOST): cv.string,
    }
)

MODE_SCHEMA = vol.Schema({vol.Optional("mode"): cv.string})


def default_options() -> dict[str, Any]:
    return {
        CONF_CHECK_INTERVAL: DEFAULT_CHECK_INTERVAL,
        CONF_FAILURES_BEFORE_REBOOT: DEFAULT_FAILURES_BEFORE_REBOOT,
        CONF_AUTO_REBOOT: DEFAULT_AUTO_REBOOT,
        CONF_REBOOT_COOLDOWN: DEFAULT_REBOOT_COOLDOWN,
        CONF_MAX_SOFT_REBOOTS_PER_DAY: DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
        CONF_HTTP_TIMEOUT: DEFAULT_HTTP_TIMEOUT,
        CONF_HARD_REBOOT_SWITCHES: {},
        CONF_HARD_REBOOT_OFF_SECONDS: DEFAULT_HARD_REBOOT_OFF_SECONDS,
        CONF_WATCHDOG_ENABLED: DEFAULT_WATCHDOG_ENABLED,
        CONF_NOTIFICATIONS_ENABLED: DEFAULT_NOTIFICATIONS_ENABLED,
        CONF_NOTIFY_SERVICE: "",
        CONF_RELOAD_DAIKIN: DEFAULT_RELOAD_DAIKIN,
        CONF_CLIMATE_ENABLED: DEFAULT_CLIMATE_ENABLED,
        CONF_SALON_TEMP_SENSOR: "",
        CONF_OUTDOOR_TEMP_SENSOR: "",
        CONF_PRESENCE_SENSOR: "",
        CONF_SUN_ENTITY: DEFAULT_SUN_ENTITY,
        CONF_NIGHT_START_HOUR: DEFAULT_NIGHT_START_HOUR,
        CONF_NIGHT_END_HOUR: DEFAULT_NIGHT_END_HOUR,
        CONF_OPENING_SENSORS: {},
        CONF_OPENING_DELAY_SECONDS: DEFAULT_OPENING_DELAY_SECONDS,
        CONF_HEAT_PRESETS: serialize_default_heat_presets(),
        CONF_COOL_PRESETS: serialize_default_cool_presets(),
        CONF_HEAT_ON_SALON_BELOW: DEFAULT_HEAT_ON_SALON_BELOW,
        CONF_HEAT_ON_OUTDOOR_BELOW: DEFAULT_HEAT_ON_OUTDOOR_BELOW,
        CONF_HEAT_OFF_SALON_ABOVE: DEFAULT_HEAT_OFF_SALON_ABOVE,
        CONF_HEAT_OFF_OUTDOOR_ABOVE: DEFAULT_HEAT_OFF_OUTDOOR_ABOVE,
        CONF_COOL_ON_SALON_ABOVE: DEFAULT_COOL_ON_SALON_ABOVE,
        CONF_COOL_ON_OUTDOOR_ABOVE: DEFAULT_COOL_ON_OUTDOOR_ABOVE,
        CONF_COOL_OFF_OUTDOOR_BELOW: DEFAULT_COOL_OFF_OUTDOOR_BELOW,
        CONF_HEAT_MODE: DEFAULT_HEAT_MODE,
        CONF_COOL_MODE: DEFAULT_COOL_MODE,
    }


def _register_services(hass: HomeAssistant) -> None:
    async def _handle_reboot(call: ServiceCall) -> None:
        coordinator = _coordinator_from_hass(hass)
        await coordinator.async_reboot_module(
            entry_id=call.data.get("entry_id"),
            host=call.data.get(CONF_HOST),
        )

    async def _handle_hard_reboot(call: ServiceCall) -> None:
        coordinator = _coordinator_from_hass(hass)
        await coordinator.async_hard_reboot_module(
            entry_id=call.data.get("entry_id"),
            host=call.data.get(CONF_HOST),
        )

    async def _handle_check_now(_call: ServiceCall) -> None:
        coordinator = _coordinator_from_hass(hass)
        await coordinator.async_request_refresh()

    async def _handle_apply_heat(call: ServiceCall) -> None:
        climate = _climate_from_hass(hass)
        mode = call.data.get("mode")
        if mode:
            await climate.async_set_heat_mode(mode)
        else:
            await climate.async_apply_heat_mode()

    async def _handle_apply_cool(call: ServiceCall) -> None:
        climate = _climate_from_hass(hass)
        mode = call.data.get("mode")
        if mode:
            await climate.async_set_cool_mode(mode)
        else:
            await climate.async_apply_cool_mode()

    async def _handle_evaluate(_call: ServiceCall) -> None:
        await _climate_from_hass(hass).async_evaluate()

    if not hass.services.has_service(DOMAIN, SERVICE_REBOOT):
        hass.services.async_register(
            DOMAIN, SERVICE_REBOOT, _handle_reboot, schema=REBOOT_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_HARD_REBOOT):
        hass.services.async_register(
            DOMAIN, SERVICE_HARD_REBOOT, _handle_hard_reboot, schema=REBOOT_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CHECK_NOW):
        hass.services.async_register(DOMAIN, SERVICE_CHECK_NOW, _handle_check_now)
    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_HEAT_MODE):
        hass.services.async_register(
            DOMAIN, SERVICE_APPLY_HEAT_MODE, _handle_apply_heat, schema=MODE_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_APPLY_COOL_MODE):
        hass.services.async_register(
            DOMAIN, SERVICE_APPLY_COOL_MODE, _handle_apply_cool, schema=MODE_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_CLIMATE_EVALUATE):
        hass.services.async_register(DOMAIN, SERVICE_CLIMATE_EVALUATE, _handle_evaluate)


def _coordinator_from_hass(hass: HomeAssistant) -> DaikinWatchdogCoordinator:
    stored = hass.data.get(DOMAIN) or {}
    if not stored:
        raise ValueError("Daikin WiFi Watchdog is not loaded")
    return next(iter(stored.values()))


def _climate_from_hass(hass: HomeAssistant) -> ClimateManager:
    coordinator = _coordinator_from_hass(hass)
    climate = getattr(coordinator, "climate", None)
    if climate is None:
        raise ValueError("Climate manager is not loaded")
    return climate


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    options = {**default_options(), **(entry.options or {})}
    # Keep nested preset defaults when user options omit them.
    if not options.get(CONF_HEAT_PRESETS):
        options[CONF_HEAT_PRESETS] = serialize_default_heat_presets()
    if not options.get(CONF_COOL_PRESETS):
        options[CONF_COOL_PRESETS] = serialize_default_cool_presets()

    coordinator = DaikinWatchdogCoordinator(hass, options, config_entry=entry)
    climate = ClimateManager(hass, coordinator, options)
    coordinator.climate = climate
    editor = PresetEditor(hass, entry, coordinator)
    coordinator.preset_editor = editor
    editor.ensure_selection()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.runtime_data = coordinator

    await coordinator.async_config_entry_first_refresh()
    await climate.async_setup()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_update_hub_device(hass, entry)
    async_cleanup_stale_entities(hass, entry, coordinator)

    @callback
    def _cleanup_stale_entities() -> None:
        async_cleanup_stale_entities(hass, entry, coordinator)

    entry.async_on_unload(coordinator.async_add_listener(_cleanup_stale_entities))

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            SIGNAL_CONFIG_ENTRY_CHANGED,
            coordinator.async_on_ha_config_entries_changed,
        )
    )
    _register_services(hass)
    return True


@callback
def _async_update_hub_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Keep the hub device firmware field in sync with manifest.json."""
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Daikin",
        name="Daikin WiFi Watchdog",
        model="WiFi Watchdog",
        sw_version=integration_version(),
        configuration_url="https://github.com/nicdive/daikin-HA-watchdog",
    )


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN][entry.entry_id]
    options = {**default_options(), **(entry.options or {})}
    if not options.get(CONF_HEAT_PRESETS):
        options[CONF_HEAT_PRESETS] = serialize_default_heat_presets()
    if not options.get(CONF_COOL_PRESETS):
        options[CONF_COOL_PRESETS] = serialize_default_cool_presets()
    coordinator.update_options(options)
    climate: ClimateManager | None = getattr(coordinator, "climate", None)
    if climate is not None:
        climate.update_options(options)
    editor = getattr(coordinator, "preset_editor", None)
    if editor is not None:
        editor.on_options_updated()
    await coordinator.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: DaikinWatchdogCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        climate: ClimateManager | None = getattr(coordinator, "climate", None)
        if climate is not None:
            await climate.async_shutdown()
        await coordinator.async_shutdown_watchdog()
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_REBOOT,
                SERVICE_HARD_REBOOT,
                SERVICE_CHECK_NOW,
                SERVICE_APPLY_HEAT_MODE,
                SERVICE_APPLY_COOL_MODE,
                SERVICE_CLIMATE_EVALUATE,
            ):
                if hass.services.has_service(DOMAIN, service):
                    hass.services.async_remove(DOMAIN, service)
            hass.data.pop(DOMAIN, None)
    return unload_ok
