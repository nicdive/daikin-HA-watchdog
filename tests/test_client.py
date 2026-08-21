from __future__ import annotations

from client import HealthStatus, parse_daikin_response
from helpers import module_url, reboot_exception_is_expected, sanitize_host


def test_parse_basic_info() -> None:
    raw = "ret=OK,type=aircon,name=%53alon,err=255,pow=0,adp_kind=2"
    data = parse_daikin_response(raw)
    assert data["ret"] == "OK"
    assert data["name"] == "Salon"
    assert data["err"] == 255
    assert data["pow"] == 0


def test_parse_empty_and_malformed() -> None:
    assert parse_daikin_response("") == {}
    assert parse_daikin_response("no-equals") == {}
    assert parse_daikin_response("=value,foo=")["foo"] == ""


def test_health_status_values() -> None:
    assert HealthStatus.OK == "ok"
    assert HealthStatus.ERROR_CODE == "error_code"
    assert HealthStatus.UNREACHABLE == "unreachable"
    assert HealthStatus.REBOOTING == "rebooting"


def test_sanitize_host() -> None:
    assert sanitize_host("192.168.1.50") == "192.168.1.50"
    assert sanitize_host("http://192.168.1.50/common/basic_info") == "192.168.1.50"
    assert sanitize_host("192.168.1.50:80") == "192.168.1.50:80"
    assert sanitize_host("2001:db8::1") == "[2001:db8::1]"


def test_module_url() -> None:
    assert module_url("192.168.1.50", "/common/basic_info") == (
        "http://192.168.1.50/common/basic_info"
    )
    assert module_url("2001:db8::1", "/common/basic_info") == (
        "http://[2001:db8::1]/common/basic_info"
    )


def test_reboot_timeout_with_empty_message_is_expected() -> None:
    assert reboot_exception_is_expected(TimeoutError())
    assert reboot_exception_is_expected(ConnectionResetError("Connection reset"))
    assert not reboot_exception_is_expected(RuntimeError("PARAM NG"))
