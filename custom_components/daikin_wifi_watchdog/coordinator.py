"""Watchdog coordinator: discovers Daikin AC entries and monitors WiFi modules."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import DaikinWifiClient, HealthResult, HealthStatus
from .const import (
    ATTR_DAIKIN_ENTRY_ID,
    ATTR_DETAIL,
    ATTR_ERROR_CODE,
    ATTR_HOST,
    ATTR_LAST_REBOOT,
    ATTR_MAC,
    ATTR_SOFT_REBOOTS_TODAY,
    CONF_AUTO_REBOOT,
    CONF_CHECK_INTERVAL,
    CONF_FAILURES_BEFORE_REBOOT,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_REBOOT_COOLDOWN,
    CONF_WATCHDOG_ENABLED,
    DAIKIN_DOMAIN,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_REBOOT_COOLDOWN,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
    ERROR_CODES_UNHEALTHY,
)

_LOGGER = logging.getLogger(__name__)

# Official Daikin integration stores MAC under this key.
KEY_MAC = "mac"


@dataclass(slots=True)
class TrackedModule:
    """One Daikin AC WiFi module discovered from the official integration."""

    entry_id: str
    host: str
    title: str
    mac: str | None = None


@dataclass
class ModuleRuntimeState:
    consecutive_failures: int = 0
    soft_reboots_today: int = 0
    soft_reboot_day: date | None = None
    cooldown_until: datetime | None = None
    last_result: HealthResult | None = None
    last_reboot: datetime | None = None
    last_reboot_kind: str | None = None


@dataclass
class ModuleSnapshot:
    module: TrackedModule
    status: str
    healthy: bool
    error_code: int | None
    detail: str
    soft_reboots_today: int
    last_reboot: datetime | None
    last_reboot_kind: str | None
    attributes: dict[str, Any] = field(default_factory=dict)


class DaikinWatchdogCoordinator(DataUpdateCoordinator[dict[str, ModuleSnapshot]]):
    """Periodically check Daikin WiFi health and auto-reboot if needed."""

    def __init__(self, hass: HomeAssistant, options: dict[str, Any]) -> None:
        self.options = dict(options)
        self._states: dict[str, ModuleRuntimeState] = {}
        self._client = DaikinWifiClient(
            async_get_clientsession(hass),
            timeout=float(self.options.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT)),
        )
        interval = int(self.options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(15, interval)),
        )

    def update_options(self, options: dict[str, Any]) -> None:
        self.options = dict(options)
        interval = int(self.options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL))
        self.update_interval = timedelta(seconds=max(15, interval))
        self._client = DaikinWifiClient(
            async_get_clientsession(self.hass),
            timeout=float(self.options.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT)),
        )

    @callback
    def discover_modules(self) -> list[TrackedModule]:
        """Pull hosts from official Daikin AC config entries."""
        modules: list[TrackedModule] = []
        for entry in self.hass.config_entries.async_entries(DAIKIN_DOMAIN):
            host = entry.data.get(CONF_HOST)
            if not host:
                continue
            mac = entry.data.get(KEY_MAC)
            if mac:
                mac = dr.format_mac(mac)
            modules.append(
                TrackedModule(
                    entry_id=entry.entry_id,
                    host=str(host),
                    title=entry.title or str(host),
                    mac=mac,
                )
            )
        return modules

    def _state_for(self, key: str) -> ModuleRuntimeState:
        if key not in self._states:
            self._states[key] = ModuleRuntimeState()
        return self._states[key]

    def _reset_daily(self, state: ModuleRuntimeState) -> None:
        today = dt_util.now().date()
        if state.soft_reboot_day != today:
            state.soft_reboot_day = today
            state.soft_reboots_today = 0

    async def _async_update_data(self) -> dict[str, ModuleSnapshot]:
        modules = self.discover_modules()
        if not modules:
            _LOGGER.debug("No Daikin AC config entries found to monitor")
            return {}

        if not bool(self.options.get(CONF_WATCHDOG_ENABLED, DEFAULT_WATCHDOG_ENABLED)):
            _LOGGER.debug("Watchdog disabled — skipping health checks")
            snapshots: dict[str, ModuleSnapshot] = {}
            for module in modules:
                state = self._state_for(module.entry_id)
                result = state.last_result or HealthResult(
                    status=HealthStatus.OK,
                    host=module.host,
                    detail="watchdog_disabled",
                )
                snap = self._snapshot(module, state, result)
                snap.attributes = {
                    **snap.attributes,
                    "watchdog_enabled": False,
                    "detail": "watchdog_disabled",
                }
                snapshots[module.entry_id] = snap
            return snapshots

        snapshots = {}
        for module in modules:
            snapshots[module.entry_id] = await self._check_and_recover(module)
        return snapshots

    @property
    def notifications_enabled(self) -> bool:
        return bool(
            self.options.get(CONF_NOTIFICATIONS_ENABLED, DEFAULT_NOTIFICATIONS_ENABLED)
        )

    async def _async_notify(self, title: str, message: str) -> None:
        if not self.notifications_enabled:
            return
        target = (self.options.get(CONF_NOTIFY_SERVICE) or "").strip()
        if not target:
            _LOGGER.debug("Notifications enabled but no notify target configured")
            return

        service_name = target.removeprefix("notify.")
        try:
            if self.hass.services.has_service("notify", service_name):
                await self.hass.services.async_call(
                    "notify",
                    service_name,
                    {"title": title, "message": message},
                    blocking=False,
                )
                return
            if target.startswith("notify.") and self.hass.services.has_service(
                "notify", "send_message"
            ):
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {
                        "entity_id": target,
                        "title": title,
                        "message": message,
                    },
                    blocking=False,
                )
                return
            _LOGGER.warning("Notify target introuvable: %s", target)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Failed to send mobile notification: %s", exc)

    async def _check_and_recover(self, module: TrackedModule) -> ModuleSnapshot:
        state = self._state_for(module.entry_id)
        now = dt_util.utcnow()

        if state.cooldown_until and now < state.cooldown_until:
            result = state.last_result or HealthResult(
                status=HealthStatus.UNREACHABLE,
                host=module.host,
                detail="cooldown",
            )
            return self._snapshot(module, state, result)

        result = await self._client.check_health(module.host, ERROR_CODES_UNHEALTHY)
        state.last_result = result

        if result.status is HealthStatus.OK:
            if state.consecutive_failures:
                _LOGGER.info(
                    "%s (%s) recovered after %s failure(s)",
                    module.title,
                    module.host,
                    state.consecutive_failures,
                )
                await self._async_notify(
                    "Daikin WiFi OK",
                    f"{module.title} est de nouveau joignable ({module.host}).",
                )
            state.consecutive_failures = 0
            return self._snapshot(module, state, result)

        state.consecutive_failures += 1
        failures_needed = int(
            self.options.get(CONF_FAILURES_BEFORE_REBOOT, DEFAULT_FAILURES_BEFORE_REBOOT)
        )
        auto = bool(self.options.get(CONF_AUTO_REBOOT, DEFAULT_AUTO_REBOOT))
        _LOGGER.warning(
            "%s (%s) unhealthy: %s (%s) failures=%s/%s",
            module.title,
            module.host,
            result.status,
            result.detail,
            state.consecutive_failures,
            failures_needed,
        )

        if state.consecutive_failures == 1:
            await self._async_notify(
                "Daikin WiFi planté",
                f"{module.title} ({module.host}) : {result.status.value} — {result.detail}",
            )

        if auto and state.consecutive_failures >= failures_needed:
            await self._recover(module, state, result.status)

        return self._snapshot(module, state, state.last_result or result)

    async def _recover(
        self,
        module: TrackedModule,
        state: ModuleRuntimeState,
        status: HealthStatus,
    ) -> None:
        self._reset_daily(state)
        hard_map: dict[str, str] = self.options.get(CONF_HARD_REBOOT_SWITCHES) or {}
        hard_switch = hard_map.get(module.entry_id) or hard_map.get(module.host)

        if status is HealthStatus.UNREACHABLE:
            if hard_switch:
                await self._hard_reboot(module, state, hard_switch, "unreachable")
            else:
                _LOGGER.error(
                    "%s unreachable and no hard_reboot switch configured",
                    module.title,
                )
                cooldown = int(
                    self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN)
                )
                state.cooldown_until = dt_util.utcnow() + timedelta(seconds=cooldown)
            return

        max_soft = int(
            self.options.get(
                CONF_MAX_SOFT_REBOOTS_PER_DAY, DEFAULT_MAX_SOFT_REBOOTS_PER_DAY
            )
        )
        if state.soft_reboots_today >= max_soft:
            _LOGGER.error(
                "%s soft-reboot daily quota reached (%s)",
                module.title,
                max_soft,
            )
            if hard_switch:
                await self._hard_reboot(module, state, hard_switch, "soft_quota")
            return

        await self._soft_reboot(module, state)

    async def _soft_reboot(
        self, module: TrackedModule, state: ModuleRuntimeState
    ) -> None:
        _LOGGER.warning("Soft-rebooting Daikin WiFi module %s (%s)", module.title, module.host)
        try:
            await self._client.reboot(module.host)
            ok = True
            detail = "soft reboot requested"
        except Exception as exc:  # noqa: BLE001
            ok = "timeout" in str(exc).lower() or "connection" in str(exc).lower()
            detail = str(exc)
            if ok:
                _LOGGER.info("%s soft reboot likely succeeded (connection closed)", module.title)
            else:
                _LOGGER.error("%s soft reboot failed: %s", module.title, exc)

        state.soft_reboots_today += 1
        state.consecutive_failures = 0
        state.last_reboot = dt_util.utcnow()
        state.last_reboot_kind = "soft"
        cooldown = int(self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN))
        state.cooldown_until = dt_util.utcnow() + timedelta(seconds=cooldown)
        self.hass.bus.async_fire(
            f"{DOMAIN}_soft_reboot",
            {
                "name": module.title,
                ATTR_HOST: module.host,
                ATTR_DAIKIN_ENTRY_ID: module.entry_id,
                "ok": ok,
                ATTR_DETAIL: detail,
            },
        )
        await self._async_notify(
            "Daikin WiFi reboot",
            f"Soft reboot de {module.title} ({module.host}) — {'OK' if ok else 'échec'}: {detail}",
        )
        # Ask official integration to reconnect after cooldown window starts.
        self.hass.async_create_task(self._reload_daikin_entry(module.entry_id, delay=cooldown))

    async def _hard_reboot(
        self,
        module: TrackedModule,
        state: ModuleRuntimeState,
        switch_entity_id: str,
        reason: str,
    ) -> None:
        _LOGGER.warning(
            "Hard-rebooting %s via %s (reason=%s)",
            module.title,
            switch_entity_id,
            reason,
        )
        try:
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": switch_entity_id},
                blocking=True,
            )
            await asyncio.sleep(15)
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": switch_entity_id},
                blocking=True,
            )
            ok = True
            detail = f"power cycle via {switch_entity_id}"
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = str(exc)
            _LOGGER.error("Hard reboot failed for %s: %s", module.title, exc)

        state.consecutive_failures = 0
        state.last_reboot = dt_util.utcnow()
        state.last_reboot_kind = "hard"
        cooldown = int(self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN))
        state.cooldown_until = dt_util.utcnow() + timedelta(seconds=max(cooldown, 180))
        self.hass.bus.async_fire(
            f"{DOMAIN}_hard_reboot",
            {
                "name": module.title,
                ATTR_HOST: module.host,
                ATTR_DAIKIN_ENTRY_ID: module.entry_id,
                "reason": reason,
                "ok": ok,
                ATTR_DETAIL: detail,
            },
        )
        await self._async_notify(
            "Daikin WiFi hard reboot",
            f"Power-cycle de {module.title} ({module.host}) raison={reason} — "
            f"{'OK' if ok else 'échec'}: {detail}",
        )
        self.hass.async_create_task(
            self._reload_daikin_entry(module.entry_id, delay=max(cooldown, 180))
        )

    async def _reload_daikin_entry(self, entry_id: str, delay: int) -> None:
        await asyncio.sleep(max(30, delay))
        if self.hass.config_entries.async_get_entry(entry_id) is None:
            return
        _LOGGER.info("Reloading Daikin AC entry %s after reboot", entry_id)
        await self.hass.config_entries.async_reload(entry_id)

    async def async_reboot_module(self, entry_id: str | None = None, host: str | None = None) -> bool:
        """Manual reboot service / button."""
        modules = self.discover_modules()
        target = None
        for module in modules:
            if entry_id and module.entry_id == entry_id:
                target = module
                break
            if host and module.host == host:
                target = module
                break
        if target is None and len(modules) == 1:
            target = modules[0]
        if target is None:
            raise ValueError("Module Daikin introuvable (entry_id/host)")

        state = self._state_for(target.entry_id)
        await self._soft_reboot(target, state)
        await self.async_request_refresh()
        return True

    def _snapshot(
        self,
        module: TrackedModule,
        state: ModuleRuntimeState,
        result: HealthResult,
    ) -> ModuleSnapshot:
        healthy = result.status is HealthStatus.OK
        return ModuleSnapshot(
            module=module,
            status=result.status.value,
            healthy=healthy,
            error_code=result.error_code,
            detail=result.detail,
            soft_reboots_today=state.soft_reboots_today,
            last_reboot=state.last_reboot,
            last_reboot_kind=state.last_reboot_kind,
            attributes={
                ATTR_HOST: module.host,
                ATTR_MAC: module.mac,
                ATTR_DAIKIN_ENTRY_ID: module.entry_id,
                ATTR_ERROR_CODE: result.error_code,
                ATTR_DETAIL: result.detail,
                ATTR_SOFT_REBOOTS_TODAY: state.soft_reboots_today,
                ATTR_LAST_REBOOT: state.last_reboot.isoformat()
                if state.last_reboot
                else None,
                "last_reboot_kind": state.last_reboot_kind,
                "consecutive_failures": state.consecutive_failures,
                "name": module.title,
            },
        )
