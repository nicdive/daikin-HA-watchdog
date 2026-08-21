from __future__ import annotations

import pytest
from aiohttp import ClientConnectionError

from client import DaikinWifiClient, HealthStatus, ModuleCredentials, parse_daikin_response


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
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
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
async def test_check_health_ok() -> None:
    session = FakeSession(
        {"http://192.168.1.50/common/basic_info": FakeResp("ret=OK,err=0,ver=1_2_3")}
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    result = await client.check_health("192.168.1.50", {255})
    assert result.status is HealthStatus.OK
    assert result.error_code == 0
    assert result.raw is not None
    assert result.raw["ver"] == "1_2_3"


@pytest.mark.asyncio
async def test_check_health_timeout() -> None:
    session = FakeSession(
        {"http://192.168.1.50/common/basic_info": TimeoutError()}
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    result = await client.check_health("192.168.1.50", {255})
    assert result.status is HealthStatus.UNREACHABLE
    assert result.detail == "timeout"


@pytest.mark.asyncio
async def test_check_health_bad_ret() -> None:
    session = FakeSession(
        {"http://192.168.1.50/common/basic_info": FakeResp("ret=PARAM NG")}
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    result = await client.check_health("192.168.1.50", {255})
    assert result.status is HealthStatus.BAD_RESPONSE


@pytest.mark.asyncio
async def test_reboot() -> None:
    session = FakeSession(
        {"http://192.168.1.50/common/reboot": FakeResp("ret=OK")}
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    data = await client.reboot("192.168.1.50")
    assert data["ret"] == "OK"


@pytest.mark.asyncio
async def test_reboot_timeout_is_success() -> None:
    session = FakeSession({"http://192.168.1.50/common/reboot": TimeoutError()})
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    data = await client.reboot("192.168.1.50")
    assert data["ret"] == "OK"
    assert data["note"] == "connection_closed"


@pytest.mark.asyncio
async def test_reboot_connection_error_is_success() -> None:
    session = FakeSession(
        {
            "http://192.168.1.50/common/reboot": ClientConnectionError(
                "connection closed"
            )
        }
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    data = await client.reboot("192.168.1.50")
    assert data["ret"] == "OK"


@pytest.mark.asyncio
async def test_uuid_uses_https_and_header() -> None:
    session = FakeSession(
        {
            "https://192.168.1.50/common/basic_info": FakeResp("ret=OK,err=0"),
        }
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    creds = ModuleCredentials(uuid="29aa-df23-4475")
    result = await client.check_health("192.168.1.50", {255}, creds)
    assert result.status is HealthStatus.OK
    url, kwargs = session.calls[0]
    assert url.startswith("https://")
    assert kwargs["headers"]["X-Daikin-uuid"] == "29aadf234475"
    assert kwargs["ssl"] is False


@pytest.mark.asyncio
async def test_password_sent_as_lpw() -> None:
    session = FakeSession(
        {"http://192.168.1.50/common/basic_info": FakeResp("ret=OK,err=0")}
    )
    client = DaikinWifiClient(session, timeout=2)  # type: ignore[arg-type]
    creds = ModuleCredentials(password="secret")
    await client.check_health("192.168.1.50", {255}, creds)
    _, kwargs = session.calls[0]
    assert kwargs["params"] == {"lpw": "secret"}


def test_parse_ok() -> None:
    assert parse_daikin_response("ret=OK,err=0")["err"] == 0
