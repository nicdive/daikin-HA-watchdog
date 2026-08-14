from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "daikin_wifi_watchdog"))

from client import DaikinWifiClient, HealthStatus, parse_daikin_response  # noqa: E402


class FakeResp:
    def __init__(self, text: str, status: int = 200) -> None:
        self.status = status
        self._text = text

    async def text(self) -> str:
        return self._text

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    def __init__(self, mapping: dict[str, FakeResp | Exception]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def get(self, url: str, timeout=None):
        self.calls.append(url)
        value = self.mapping[url]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.mark.asyncio
async def test_check_health_err_255() -> None:
    session = FakeSession(
        {
            "http://192.168.1.50/common/basic_info": FakeResp(
                "ret=OK,err=255,name=salon"
            )
        }
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    result = await client.check_health("192.168.1.50", {255})
    assert result.status is HealthStatus.ERROR_CODE
    assert result.error_code == 255


@pytest.mark.asyncio
async def test_reboot() -> None:
    session = FakeSession(
        {"http://192.168.1.50/common/reboot": FakeResp("ret=OK")}
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    data = await client.reboot("192.168.1.50")
    assert data["ret"] == "OK"


def test_parse_ok() -> None:
    assert parse_daikin_response("ret=OK,err=0")["err"] == 0
