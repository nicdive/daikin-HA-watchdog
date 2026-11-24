"""Async HTTP helpers for Daikin WiFi modules (local API)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import unquote

from aiohttp import ClientError, ClientSession, ClientTimeout, ContentTypeError

try:
    from .helpers import module_url, reboot_exception_is_expected
except ImportError:  # unit tests
    from helpers import module_url, reboot_exception_is_expected

_INT_KEYS = {
    "err",
    "pow",
    "port",
    "adp_kind",
    "pv",
    "cpv",
    "led",
    "notice_ip_int",
    "notice_sync_int",
}

_MAX_BODY_CHARS = 4096


class HealthStatus(StrEnum):
    OK = "ok"
    ERROR_CODE = "error_code"
    UNREACHABLE = "unreachable"
    BAD_RESPONSE = "bad_response"
    DISABLED = "disabled"
    REBOOTING = "rebooting"


@dataclass(slots=True)
class HealthResult:
    status: HealthStatus
    host: str
    error_code: int | None = None
    raw: dict[str, Any] | None = None
    detail: str = ""


@dataclass(slots=True, frozen=True)
class ModuleCredentials:
    """Auth copied from the official Daikin AC config entry."""

    password: str | None = None
    uuid: str | None = None
    api_key: str | None = None

    @property
    def use_https(self) -> bool:
        return bool(self.uuid or self.api_key)


def parse_daikin_response(body: str) -> dict[str, Any]:
    """Parse ret=OK,err=255,name=%53alon... into a dict."""
    result: dict[str, Any] = {}
    text = (body or "").strip()
    if not text:
        return result
    for part in text.split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = unquote(value.strip())
        if key in _INT_KEYS:
            try:
                result[key] = int(value)
            except ValueError:
                result[key] = value
        else:
            result[key] = value
    return result


class DaikinWifiClient:
    """Minimal local client: basic_info + reboot."""

    def __init__(self, session: ClientSession, timeout: float = 8.0) -> None:
        timeout = max(2.0, float(timeout))
        connect = min(5.0, timeout)
        self._session = session
        self._timeout = ClientTimeout(total=timeout, sock_connect=connect)

    def _headers(self, creds: ModuleCredentials | None) -> dict[str, str]:
        if not creds or not creds.uuid:
            return {}
        uuid = creds.uuid.replace("-", "").strip()
        return {"X-Daikin-uuid": uuid} if uuid else {}

    def _params(self, creds: ModuleCredentials | None) -> dict[str, str]:
        if not creds or not creds.password:
            return {}
        return {"lpw": creds.password}

    async def _get(
        self,
        host: str,
        path: str,
        creds: ModuleCredentials | None,
        *,
        https: bool,
    ) -> str:
        kwargs: dict[str, Any] = {
            "timeout": self._timeout,
            "headers": self._headers(creds),
            "params": self._params(creds) or None,
        }
        if https:
            kwargs["ssl"] = False
        async with self._session.get(module_url(host, path, https=https), **kwargs) as response:
            if response.status >= 400:
                response.raise_for_status()
            return await response.text()

    async def _get_with_scheme_fallback(
        self,
        host: str,
        path: str,
        creds: ModuleCredentials | None,
    ) -> str:
        prefer_https = bool(creds and creds.use_https)
        try:
            return await self._get(host, path, creds, https=prefer_https)
        except ClientError:
            if creds is None:
                raise
            return await self._get(host, path, creds, https=not prefer_https)

    async def get_basic_info(
        self, host: str, creds: ModuleCredentials | None = None
    ) -> dict[str, Any]:
        text = await self._get_with_scheme_fallback(host, "/common/basic_info", creds)
        data = parse_daikin_response(text[:_MAX_BODY_CHARS])
        ret = data.get("ret")
        if ret not in (None, "OK"):
            raise RuntimeError(f"Invalid Daikin response: {text[:200]}")
        if not data:
            raise RuntimeError("Empty Daikin response")
        return data

    async def reboot(
        self, host: str, creds: ModuleCredentials | None = None
    ) -> dict[str, Any]:
        """Soft-reboot WiFi module via /common/reboot."""
        try:
            text = await self._get_with_scheme_fallback(host, "/common/reboot", creds)
        except (TimeoutError, ClientError, ContentTypeError) as exc:
            if reboot_exception_is_expected(exc):
                return {"ret": "OK", "note": "connection_closed", "detail": type(exc).__name__}
            raise
        if not text.strip():
            return {"ret": "OK"}
        parsed = parse_daikin_response(text[:_MAX_BODY_CHARS])
        return parsed or {"ret": "OK"}

    async def _get_with_params(
        self,
        host: str,
        path: str,
        creds: ModuleCredentials | None,
        extra_params: dict[str, str],
        *,
        https: bool,
    ) -> str:
        params = dict(self._params(creds))
        params.update(extra_params)
        kwargs: dict[str, Any] = {
            "timeout": self._timeout,
            "headers": self._headers(creds),
            "params": params or None,
        }
        if https:
            kwargs["ssl"] = False
        async with self._session.get(module_url(host, path, https=https), **kwargs) as response:
            if response.status >= 400:
                response.raise_for_status()
            return await response.text()

    async def set_control_info(
        self,
        host: str,
        *,
        power: bool,
        mode: str | None = None,
        temp: float | None = None,
        fan_rate: str | None = None,
        fan_dir: str | None = None,
        humidity: str = "0",
        creds: ModuleCredentials | None = None,
    ) -> dict[str, Any]:
        """Apply /aircon/set_control_info (local Daikin REST)."""
        params: dict[str, str] = {"pow": "1" if power else "0"}
        if power:
            if mode is not None:
                params["mode"] = str(mode)
            if temp is not None:
                # Daikin expects one decimal place (e.g. 20.0).
                params["stemp"] = f"{float(temp):.1f}"
            params["shum"] = humidity
            if fan_rate is not None:
                params["f_rate"] = str(fan_rate)
            if fan_dir is not None:
                params["f_dir"] = str(fan_dir)

        prefer_https = bool(creds and creds.use_https)
        try:
            text = await self._get_with_params(
                host, "/aircon/set_control_info", creds, params, https=prefer_https
            )
        except ClientError:
            if creds is None:
                raise
            text = await self._get_with_params(
                host, "/aircon/set_control_info", creds, params, https=not prefer_https
            )
        data = parse_daikin_response(text[:_MAX_BODY_CHARS])
        ret = data.get("ret")
        if ret not in (None, "OK"):
            raise RuntimeError(f"Invalid set_control_info response: {text[:200]}")
        return data or {"ret": "OK"}

    async def check_health(
        self,
        host: str,
        error_codes: set[int],
        creds: ModuleCredentials | None = None,
    ) -> HealthResult:
        try:
            info = await self.get_basic_info(host, creds)
        except TimeoutError as exc:
            return HealthResult(
                status=HealthStatus.UNREACHABLE,
                host=host,
                detail=str(exc) or "timeout",
            )
        except ClientError as exc:
            return HealthResult(
                status=HealthStatus.UNREACHABLE,
                host=host,
                detail=str(exc) or type(exc).__name__,
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=HealthStatus.BAD_RESPONSE,
                host=host,
                detail=str(exc) or type(exc).__name__,
            )

        err = info.get("err")
        if isinstance(err, int) and err in error_codes:
            return HealthResult(
                status=HealthStatus.ERROR_CODE,
                host=host,
                error_code=err,
                raw=info,
                detail=f"err={err}",
            )
        return HealthResult(
            status=HealthStatus.OK,
            host=host,
            error_code=err if isinstance(err, int) else None,
            raw=info,
        )
