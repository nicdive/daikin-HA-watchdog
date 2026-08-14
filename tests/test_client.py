from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "daikin_wifi_watchdog"))

from client import HealthStatus, parse_daikin_response  # noqa: E402


def test_parse_basic_info() -> None:
    raw = "ret=OK,type=aircon,name=%53alon,err=255,pow=0,adp_kind=2"
    data = parse_daikin_response(raw)
    assert data["ret"] == "OK"
    assert data["name"] == "Salon"
    assert data["err"] == 255
    assert data["pow"] == 0


def test_health_status_values() -> None:
    assert HealthStatus.OK == "ok"
    assert HealthStatus.ERROR_CODE == "error_code"
    assert HealthStatus.UNREACHABLE == "unreachable"
