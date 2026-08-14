"""Async HTTP helpers for Daikin WiFi modules (local API)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import unquote

from aiohttp import ClientError, ClientSession, ClientTimeout


class HealthStatus(StrEnum):
    OK = "ok"
    ERROR_CODE = "error_code"
    UNREACHABLE = "unreachable"
    BAD_RESPONSE = "bad_response"


@dataclass(slots=True)
class HealthResult:
    status: HealthStatus
    host: str
    error_code: int | None = None
    raw: dict[str, Any] | None = None
    detail: str = ""


def parse_daikin_response(body: str) -> dict[str, Any]:
    """Parse ret=OK,err=255,name=%53alon... into a dict."""
    result: dict[str, Any] = {}
    for part in body.strip().split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = unquote(value.strip())
        if key in {"err", "pow", "port", "adp_kind", "pv", "cpv", "led"}:
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
        self._session = session
        self._timeout = ClientTimeout(total=timeout)

    def _url(self, host: str, path: str) -> str:
        host = host.strip().removeprefix("http://").removeprefix("https://")
        return f"http://{host}{path}"

    async def get_basic_info(self, host: str) -> dict[str, Any]:
        async with self._session.get(
            self._url(host, "/common/basic_info"),
            timeout=self._timeout,
        ) as response:
            response.raise_for_status()
            text = await response.text()
        data = parse_daikin_response(text)
        if data.get("ret") not in (None, "OK"):
            raise RuntimeError(f"Invalid Daikin response: {text[:200]}")
        return data

    async def reboot(self, host: str) -> dict[str, Any]:
        """Soft-reboot WiFi module via /common/reboot."""
        try:
            async with self._session.get(
                self._url(host, "/common/reboot"),
                timeout=self._timeout,
            ) as response:
                text = await response.text()
                if response.status >= 400:
                    response.raise_for_status()
        except ClientError:
            # Connection drop during reboot is common/expected.
            return {"ret": "OK", "note": "connection_closed"}
        if not text.strip():
            return {"ret": "OK"}
        return parse_daikin_response(text)

    async def check_health(
        self, host: str, error_codes: set[int]
    ) -> HealthResult:
        try:
            info = await self.get_basic_info(host)
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
                detail=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            return HealthResult(
                status=HealthStatus.BAD_RESPONSE,
                host=host,
                detail=str(exc),
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
