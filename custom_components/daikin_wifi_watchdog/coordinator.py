"""Watchdog coordinator: discovers Daikin AC entries and monitors WiFi modules."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import SOURCE_IGNORE, ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PASSWORD, CONF_UUID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import DaikinWifiClient, HealthResult, HealthStatus, ModuleCredentials
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
    CONF_HARD_REBOOT_OFF_SECONDS,
    CONF_HARD_REBOOT_SWITCHES,
    CONF_HTTP_TIMEOUT,
    CONF_MAX_SOFT_REBOOTS_PER_DAY,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_NOTIFY_SERVICE,
    CONF_REBOOT_COOLDOWN,
    CONF_RELOAD_DAIKIN,
    CONF_WATCHDOG_ENABLED,
    DAIKIN_DOMAIN,
    DEFAULT_AUTO_REBOOT,
    DEFAULT_CHECK_INTERVAL,
    DEFAULT_FAILURES_BEFORE_REBOOT,
    DEFAULT_HARD_REBOOT_OFF_SECONDS,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_MAX_SOFT_REBOOTS_PER_DAY,
    DEFAULT_NOTIFICATIONS_ENABLED,
    DEFAULT_REBOOT_COOLDOWN,
    DEFAULT_RELOAD_DAIKIN,
    DEFAULT_WATCHDOG_ENABLED,
    DOMAIN,
    ERROR_CODES_UNHEALTHY,
    KEY_MAC,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .recovery import RecoveryAction, daily_counter_should_reset, decide_recovery
from .helpers import reboot_exception_is_expected

_LOGGER = logging.getLogger(__name__)

_TRANSIENT_RETRY_DELAY = 1.0


@dataclass(slots=True)
class TrackedModule:
    """One Daikin AC WiFi module discovered from the official integration."""

    entry_id: str
    host: str
    title: str
    mac: str | None = None
    creds: ModuleCredentials | None = None
    disabled: bool = False


@dataclass
class ModuleRuntimeState:
    consecutive_failures: int = 0
    soft_reboots_today: int = 0
    soft_reboot_day: date | None = None
    cooldown_until: datetime | None = None
    last_result: HealthResult | None = None
    last_reboot: datetime | None = None
    last_reboot_kind: str | None = None
    last_ok_notified: bool = True
    recovery_in_progress: bool = False


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
    consecutive_failures: int = 0
    in_cooldown: bool = False
    attributes: dict[str, Any] = field(default_factory=dict)


class DaikinWatchdogCoordinator(DataUpdateCoordinator[dict[str, ModuleSnapshot]]):
    """Periodically check Daikin WiFi health and auto-reboot if needed."""

    def __init__(
        self,
        hass: HomeAssistant,
        options: dict[str, Any],
        config_entry: ConfigEntry | None = None,
    ) -> None:
        self.options = dict(options)
        self.config_entry = config_entry
        self._states: dict[str, ModuleRuntimeState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._unloaded = False
        self._states_loaded = False
        self._discover_unsub: Callable[[], None] | None = None
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._logged_missing_notify = False
        interval = int(self.options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(15, interval)),
        )
        self._client = self._build_client()

    def _build_client(self) -> DaikinWifiClient:
        return DaikinWifiClient(
            async_get_clientsession(self.hass),
            timeout=float(self.options.get(CONF_HTTP_TIMEOUT, DEFAULT_HTTP_TIMEOUT)),
        )

    def update_options(self, options: dict[str, Any]) -> None:
        self.options = dict(options)
        interval = int(self.options.get(CONF_CHECK_INTERVAL, DEFAULT_CHECK_INTERVAL))
        self.update_interval = timedelta(seconds=max(15, interval))
        self._client = self._build_client()

    async def async_shutdown_watchdog(self) -> None:
        """Cancel background recovery/reload tasks when the integration unloads."""
        self._unloaded = True
        if self._discover_unsub is not None:
            self._discover_unsub()
            self._discover_unsub = None
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()
        await self._async_save_states()

    def _track_task(self, coro: Any) -> asyncio.Task[Any]:
        task = self.hass.async_create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _lock_for(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _is_french(self) -> bool:
        language = (getattr(self.hass.config, "language", None) or "en").lower()
        return language.startswith("fr")

    def _msg(self, fr: str, en: str) -> str:
        return fr if self._is_french() else en

    @callback
    def async_on_ha_config_entries_changed(self) -> None:
        if self._unloaded:
            return
        if self._discover_unsub is not None:
            self._discover_unsub()

        @callback
        def _run(_now: datetime) -> None:
            self._discover_unsub = None
            if not self._unloaded:
                self.hass.async_create_task(self.async_request_refresh())

        self._discover_unsub = async_call_later(self.hass, 2.0, _run)

    @callback
    def discover_modules(self) -> list[TrackedModule]:
        """Pull hosts from official Daikin AC config entries."""
        modules: list[TrackedModule] = []
        for entry in self.hass.config_entries.async_entries(DAIKIN_DOMAIN):
            if entry.source == SOURCE_IGNORE:
                continue
            host = entry.data.get(CONF_HOST)
            if not host:
                continue
            mac = entry.data.get(KEY_MAC) or entry.unique_id
            if mac:
                try:
                    mac = dr.format_mac(str(mac))
                except (TypeError, ValueError):
                    mac = str(mac)
            password = entry.data.get(CONF_PASSWORD) or None
            uuid = entry.data.get(CONF_UUID) or None
            api_key = entry.data.get(CONF_API_KEY) or None
            creds = None
            if password or uuid or api_key:
                creds = ModuleCredentials(
                    password=str(password) if password else None,
                    uuid=str(uuid) if uuid else None,
                    api_key=str(api_key) if api_key else None,
                )
            modules.append(
                TrackedModule(
                    entry_id=entry.entry_id,
                    host=str(host),
                    title=entry.title or str(host),
                    mac=mac,
                    creds=creds,
                    disabled=entry.disabled_by is not None,
                )
            )
        return modules

    def _state_for(self, key: str) -> ModuleRuntimeState:
        if key not in self._states:
            self._states[key] = ModuleRuntimeState()
        return self._states[key]

    def _reset_daily(self, state: ModuleRuntimeState) -> None:
        today = dt_util.now().date()
        stored = state.soft_reboot_day.isoformat() if state.soft_reboot_day else None
        if daily_counter_should_reset(stored, today.isoformat()):
            state.soft_reboot_day = today
            state.soft_reboots_today = 0

    async def _async_load_states(self) -> None:
        if self._states_loaded:
            return
        self._states_loaded = True
        data = await self._store.async_load()
        if not data:
            return
        modules = data.get("modules") if isinstance(data, dict) else None
        if not isinstance(modules, dict):
            return
        for key, raw in modules.items():
            if not isinstance(raw, dict):
                continue
            state = self._state_for(str(key))
            state.soft_reboots_today = int(raw.get("soft_reboots_today") or 0)
            day = raw.get("soft_reboot_day")
            if isinstance(day, str):
                try:
                    state.soft_reboot_day = date.fromisoformat(day)
                except ValueError:
                    state.soft_reboot_day = None
            last = raw.get("last_reboot")
            if isinstance(last, str):
                parsed = dt_util.parse_datetime(last)
                if parsed is not None:
                    state.last_reboot = dt_util.as_utc(parsed)
            kind = raw.get("last_reboot_kind")
            if isinstance(kind, str):
                state.last_reboot_kind = kind
            self._reset_daily(state)

    async def _async_save_states(self) -> None:
        payload = {
            "modules": {
                key: {
                    "soft_reboots_today": state.soft_reboots_today,
                    "soft_reboot_day": state.soft_reboot_day.isoformat()
                    if state.soft_reboot_day
                    else None,
                    "last_reboot": state.last_reboot.isoformat()
                    if state.last_reboot
                    else None,
                    "last_reboot_kind": state.last_reboot_kind,
                }
                for key, state in self._states.items()
            }
        }
        await self._store.async_save(payload)

    async def _async_update_data(self) -> dict[str, ModuleSnapshot]:
        await self._async_load_states()
        modules = self.discover_modules()
        if not modules:
            _LOGGER.debug("No Daikin AC config entries found to monitor")
            return {}

        enabled_modules = [module for module in modules if not module.disabled]
        if not enabled_modules:
            _LOGGER.debug("All discovered Daikin AC entries are disabled")
            return {}

        if not bool(self.options.get(CONF_WATCHDOG_ENABLED, DEFAULT_WATCHDOG_ENABLED)):
            _LOGGER.debug("Watchdog disabled — skipping health checks")
            snapshots: dict[str, ModuleSnapshot] = {}
            for module in enabled_modules:
                state = self._state_for(module.entry_id)
                self._reset_daily(state)
                result = state.last_result or HealthResult(
                    status=HealthStatus.DISABLED,
                    host=module.host,
                    detail="watchdog_disabled",
                )
                snapshots[module.entry_id] = self._snapshot(
                    module, state, result, watchdog_enabled=False
                )
            return snapshots

        results = await asyncio.gather(
            *(self._check_and_recover(module) for module in enabled_modules),
            return_exceptions=True,
        )
        snapshots = {}
        for module, result in zip(enabled_modules, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.exception(
                    "Health check failed for %s (%s): %s",
                    module.title,
                    module.host,
                    result,
                )
                state = self._state_for(module.entry_id)
                fallback = HealthResult(
                    status=HealthStatus.UNREACHABLE,
                    host=module.host,
                    detail=str(result) or type(result).__name__,
                )
                snapshots[module.entry_id] = self._snapshot(module, state, fallback)
            else:
                snapshots[module.entry_id] = result
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
            if not self._logged_missing_notify:
                _LOGGER.debug("Notifications enabled but no notify target configured")
                self._logged_missing_notify = True
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
            if self.hass.services.has_service("notify", "send_message"):
                entity_id = target if target.startswith("notify.") else f"notify.{target}"
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {
                        "entity_id": entity_id,
                        "title": title,
                        "message": message,
                    },
                    blocking=False,
                )
                return
            _LOGGER.warning("Notify target not found: %s", target)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Failed to send mobile notification: %s", exc)

    def _hard_switch_for(self, module: TrackedModule) -> str | None:
        hard_map: dict[str, str] = self.options.get(CONF_HARD_REBOOT_SWITCHES) or {}
        return hard_map.get(module.entry_id) or hard_map.get(module.host) or None

    async def _check_and_recover(self, module: TrackedModule) -> ModuleSnapshot:
        async with self._lock_for(module.entry_id):
            return await self._async_check_and_recover_locked(module)

    async def _async_check_and_recover_locked(self, module: TrackedModule) -> ModuleSnapshot:
        state = self._state_for(module.entry_id)
        self._reset_daily(state)
        now = dt_util.utcnow()

        if state.recovery_in_progress or (
            state.cooldown_until and now < state.cooldown_until
        ):
            if state.last_reboot and state.cooldown_until:
                result = HealthResult(
                    status=HealthStatus.REBOOTING,
                    host=module.host,
                    error_code=state.last_result.error_code if state.last_result else None,
                    detail="cooldown",
                )
            else:
                result = state.last_result or HealthResult(
                    status=HealthStatus.UNREACHABLE,
                    host=module.host,
                    detail="cooldown",
                )
            return self._snapshot(module, state, result)

        result = await self._client.check_health(
            module.host, ERROR_CODES_UNHEALTHY, module.creds
        )
        if result.status is HealthStatus.UNREACHABLE:
            await asyncio.sleep(_TRANSIENT_RETRY_DELAY)
            if self._unloaded:
                return self._snapshot(module, state, result)
            retry = await self._client.check_health(
                module.host, ERROR_CODES_UNHEALTHY, module.creds
            )
            if retry.status is not HealthStatus.UNREACHABLE:
                result = retry

        state.last_result = result
        self._async_ensure_device(module, result)
        self._update_device_from_health(module, result)

        if result.status is HealthStatus.OK:
            if state.consecutive_failures:
                _LOGGER.info(
                    "%s (%s) recovered after %s failure(s)",
                    module.title,
                    module.host,
                    state.consecutive_failures,
                )
                if not state.last_ok_notified:
                    await self._async_notify(
                        self._msg("Daikin WiFi OK", "Daikin WiFi OK"),
                        self._msg(
                            f"{module.title} est de nouveau joignable ({module.host}).",
                            f"{module.title} is reachable again ({module.host}).",
                        ),
                    )
            state.consecutive_failures = 0
            state.last_ok_notified = True
            self._async_clear_issue(module.entry_id)
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
            state.last_ok_notified = False
            await self._async_notify(
                self._msg("Daikin WiFi planté", "Daikin WiFi down"),
                f"{module.title} ({module.host}) : {result.status.value} — {result.detail}",
            )

        action = decide_recovery(
            status=result.status,
            auto_reboot=auto,
            consecutive_failures=state.consecutive_failures,
            failures_needed=failures_needed,
            soft_reboots_today=state.soft_reboots_today,
            max_soft_reboots=int(
                self.options.get(
                    CONF_MAX_SOFT_REBOOTS_PER_DAY, DEFAULT_MAX_SOFT_REBOOTS_PER_DAY
                )
            ),
            has_hard_switch=bool(self._hard_switch_for(module)),
        )
        if action is not RecoveryAction.NONE:
            await self._recover(module, state, result.status, action)

        return self._snapshot(module, state, state.last_result or result)

    def _async_ensure_device(
        self, module: TrackedModule, result: HealthResult | None = None
    ) -> None:
        if self.config_entry is None:
            return
        dev_reg = dr.async_get(self.hass)
        if dev_reg.async_get_device(identifiers={(DOMAIN, module.entry_id)}) is not None:
            return
        info: dict[str, Any] = {
            "config_entry_id": self.config_entry.entry_id,
            "identifiers": {(DOMAIN, module.entry_id)},
            "manufacturer": "Daikin",
            "name": module.title,
            "model": "WiFi module",
        }
        if module.mac:
            info["connections"] = {(dr.CONNECTION_NETWORK_MAC, module.mac)}
        if module.host:
            info["configuration_url"] = f"http://{module.host}/common/basic_info"
        raw = (result.raw if result else None) or {}
        if raw.get("ver"):
            info["sw_version"] = str(raw["ver"])
        dr.async_get(self.hass).async_get_or_create(**info)

    def _update_device_from_health(self, module: TrackedModule, result: HealthResult) -> None:
        raw = result.raw or {}
        if not raw:
            return
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(identifiers={(DOMAIN, module.entry_id)})
        if device is None:
            return
        updates: dict[str, Any] = {}
        ver = raw.get("ver")
        if ver:
            updates["sw_version"] = str(ver)
        model = raw.get("adp_kind")
        if model is not None:
            updates["model"] = f"WiFi module (adp_kind={model})"
        mac = raw.get("mac") or module.mac
        if mac:
            try:
                formatted = dr.format_mac(str(mac))
            except (TypeError, ValueError):
                formatted = str(mac)
            updates["new_connections"] = set(device.connections) | {
                (dr.CONNECTION_NETWORK_MAC, formatted)
            }
        if updates:
            dev_reg.async_update_device(device.id, **updates)

    def _async_create_issue(
        self, module: TrackedModule, issue_id: str, translation_key: str, **placeholders: str
    ) -> None:
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{issue_id}_{module.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=translation_key,
            translation_placeholders={"name": module.title, "host": module.host, **placeholders},
        )

    def _async_clear_issue(self, daikin_entry_id: str) -> None:
        for key in ("quota", "unreachable"):
            ir.async_delete_issue(self.hass, DOMAIN, f"{key}_{daikin_entry_id}")

    async def _recover(
        self,
        module: TrackedModule,
        state: ModuleRuntimeState,
        status: HealthStatus,
        action: RecoveryAction,
    ) -> None:
        hard_switch = self._hard_switch_for(module)
        cooldown = int(self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN))

        if action is RecoveryAction.HARD and not hard_switch:
            action = RecoveryAction.WAIT

        if action is RecoveryAction.WAIT:
            _LOGGER.error(
                "%s unhealthy (%s) and no hard-reboot switch configured",
                module.title,
                status,
            )
            state.cooldown_until = dt_util.utcnow() + timedelta(seconds=cooldown)
            if status is HealthStatus.UNREACHABLE:
                self._async_create_issue(module, "unreachable", "module_unreachable")
            else:
                self._async_create_issue(
                    module,
                    "quota",
                    "soft_reboot_quota",
                    max=str(
                        self.options.get(
                            CONF_MAX_SOFT_REBOOTS_PER_DAY, DEFAULT_MAX_SOFT_REBOOTS_PER_DAY
                        )
                    ),
                )
            return

        if action is RecoveryAction.HARD:
            assert hard_switch is not None
            reason = "unreachable" if status is HealthStatus.UNREACHABLE else "soft_quota"
            if reason == "soft_quota":
                self._async_create_issue(
                    module,
                    "quota",
                    "soft_reboot_quota",
                    max=str(
                        self.options.get(
                            CONF_MAX_SOFT_REBOOTS_PER_DAY, DEFAULT_MAX_SOFT_REBOOTS_PER_DAY
                        )
                    ),
                )
            await self._hard_reboot(module, state, hard_switch, reason)
            return

        if action is RecoveryAction.SOFT:
            await self._soft_reboot(module, state)

    async def _soft_reboot(
        self, module: TrackedModule, state: ModuleRuntimeState
    ) -> None:
        _LOGGER.warning("Soft-rebooting Daikin WiFi module %s (%s)", module.title, module.host)
        try:
            await self._client.reboot(module.host, module.creds)
            ok = True
            detail = "soft reboot requested"
        except Exception as exc:  # noqa: BLE001
            ok = reboot_exception_is_expected(exc)
            detail = str(exc) or type(exc).__name__
            if ok:
                _LOGGER.info("%s soft reboot likely succeeded (connection closed)", module.title)
            else:
                _LOGGER.error("%s soft reboot failed: %s", module.title, exc)

        if ok:
            state.soft_reboots_today += 1
            state.consecutive_failures = 0
            state.last_reboot = dt_util.utcnow()
            state.last_reboot_kind = "soft"
            cooldown = int(self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN))
            state.cooldown_until = dt_util.utcnow() + timedelta(seconds=cooldown)
            self.hass.async_create_task(self._async_save_states())
            if bool(self.options.get(CONF_RELOAD_DAIKIN, DEFAULT_RELOAD_DAIKIN)):
                self._track_task(self._reload_daikin_entry(module.entry_id, delay=cooldown))
        else:
            # Keep failure count so the next cycle can escalate to a hard reboot.
            cooldown = min(
                30, int(self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN))
            )
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
            self._msg("Daikin WiFi reboot", "Daikin WiFi reboot"),
            self._msg(
                f"Soft reboot de {module.title} ({module.host}) — {'OK' if ok else 'échec'}: {detail}",
                f"Soft reboot of {module.title} ({module.host}) — {'OK' if ok else 'failed'}: {detail}",
            ),
        )

    async def _hard_reboot(
        self,
        module: TrackedModule,
        state: ModuleRuntimeState,
        switch_entity_id: str,
        reason: str,
    ) -> None:
        cooldown = int(self.options.get(CONF_REBOOT_COOLDOWN, DEFAULT_REBOOT_COOLDOWN))
        off_seconds = int(
            self.options.get(CONF_HARD_REBOOT_OFF_SECONDS, DEFAULT_HARD_REBOOT_OFF_SECONDS)
        )
        state.recovery_in_progress = True
        state.consecutive_failures = 0
        state.last_reboot = dt_util.utcnow()
        state.last_reboot_kind = "hard"
        state.cooldown_until = dt_util.utcnow() + timedelta(seconds=max(cooldown, 180))
        self.hass.async_create_task(self._async_save_states())
        self._track_task(
            self._async_run_hard_reboot(
                module, switch_entity_id, reason, off_seconds, max(cooldown, 180)
            )
        )

    async def _async_run_hard_reboot(
        self,
        module: TrackedModule,
        switch_entity_id: str,
        reason: str,
        off_seconds: int,
        reload_delay: int,
    ) -> None:
        state = self._state_for(module.entry_id)
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
            await asyncio.sleep(max(5, off_seconds))
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": switch_entity_id},
                blocking=True,
            )
            ok = True
            detail = f"power cycle via {switch_entity_id}"
        except asyncio.CancelledError:
            state.recovery_in_progress = False
            raise
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = str(exc) or type(exc).__name__
            _LOGGER.error("Hard reboot failed for %s: %s", module.title, exc)

        state.recovery_in_progress = False
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
            self._msg("Daikin WiFi hard reboot", "Daikin WiFi hard reboot"),
            self._msg(
                f"Power-cycle de {module.title} ({module.host}) raison={reason} — "
                f"{'OK' if ok else 'échec'}: {detail}",
                f"Power-cycle of {module.title} ({module.host}) reason={reason} — "
                f"{'OK' if ok else 'failed'}: {detail}",
            ),
        )
        if ok and bool(self.options.get(CONF_RELOAD_DAIKIN, DEFAULT_RELOAD_DAIKIN)):
            await self._reload_daikin_entry(module.entry_id, delay=reload_delay)

    async def _reload_daikin_entry(self, entry_id: str, delay: int) -> None:
        await asyncio.sleep(max(30, delay))
        if self._unloaded:
            return
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.disabled_by is not None:
            return
        _LOGGER.info("Reloading Daikin AC entry %s after reboot", entry_id)
        try:
            await self.hass.config_entries.async_reload(entry_id)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Failed to reload Daikin AC entry %s: %s", entry_id, exc)

    def _resolve_module(
        self, entry_id: str | None = None, host: str | None = None
    ) -> TrackedModule:
        modules = [module for module in self.discover_modules() if not module.disabled]
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
            raise ValueError("Daikin module not found (entry_id/host)")
        return target

    async def async_reboot_module(
        self, entry_id: str | None = None, host: str | None = None
    ) -> bool:
        """Manual reboot service / button."""
        target = self._resolve_module(entry_id, host)
        async with self._lock_for(target.entry_id):
            state = self._state_for(target.entry_id)
            await self._soft_reboot(target, state)
        await self.async_request_refresh()
        return True

    async def async_hard_reboot_module(
        self, entry_id: str | None = None, host: str | None = None
    ) -> bool:
        """Manual power-cycle via the mapped smart plug."""
        target = self._resolve_module(entry_id, host)
        hard_switch = self._hard_switch_for(target)
        if not hard_switch:
            raise ValueError(f"No hard-reboot switch configured for {target.title}")
        async with self._lock_for(target.entry_id):
            state = self._state_for(target.entry_id)
            await self._hard_reboot(target, state, hard_switch, "manual")
        await self.async_request_refresh()
        return True

    def _snapshot(
        self,
        module: TrackedModule,
        state: ModuleRuntimeState,
        result: HealthResult,
        *,
        watchdog_enabled: bool = True,
    ) -> ModuleSnapshot:
        now = dt_util.utcnow()
        in_cooldown = bool(
            state.recovery_in_progress
            or (state.cooldown_until and now < state.cooldown_until)
        )
        cooldown_remaining = None
        if state.cooldown_until and now < state.cooldown_until:
            cooldown_remaining = int((state.cooldown_until - now).total_seconds())
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
            consecutive_failures=state.consecutive_failures,
            in_cooldown=in_cooldown,
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
                "watchdog_enabled": watchdog_enabled,
                "in_cooldown": in_cooldown,
                "cooldown_remaining": cooldown_remaining,
                "has_hard_reboot_switch": bool(self._hard_switch_for(module)),
                "adapter_version": (result.raw or {}).get("ver"),
            },
        )

    def snapshot_as_dict(self, snap: ModuleSnapshot) -> dict[str, Any]:
        return {
            "title": snap.module.title,
            "host": snap.module.host,
            "mac": snap.module.mac,
            "status": snap.status,
            "healthy": snap.healthy,
            "error_code": snap.error_code,
            "detail": snap.detail,
            "soft_reboots_today": snap.soft_reboots_today,
            "last_reboot": snap.last_reboot.isoformat() if snap.last_reboot else None,
            "last_reboot_kind": snap.last_reboot_kind,
            "consecutive_failures": snap.consecutive_failures,
            "in_cooldown": snap.in_cooldown,
            "attributes": {
                key: value
                for key, value in snap.attributes.items()
                if key not in {"mac"}
            },
        }
