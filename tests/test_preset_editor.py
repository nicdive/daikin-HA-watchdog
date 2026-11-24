"""Unit tests for preset override storage used by the dashboard editor."""

from __future__ import annotations

from climate_defaults import (
    DEFAULT_HEAT_PRESETS,
    DeviceSetpoint,
    presets_from_dict,
    presets_to_dict,
)


def test_default_confort_salon_setpoint() -> None:
    presets = presets_to_dict(DEFAULT_HEAT_PRESETS)
    salon = DeviceSetpoint.from_dict(presets["confort"]["salon"])
    assert salon.power is True
    assert salon.temp == 20.0


def test_entry_id_override_wins() -> None:
    raw = presets_to_dict(DEFAULT_HEAT_PRESETS)
    raw["confort"]["entry-abc"] = {
        "power": True,
        "temp": 21.5,
        "mode": "4",
        "fan_rate": "B",
        "fan_dir": "0",
    }
    merged = presets_from_dict(raw, DEFAULT_HEAT_PRESETS)
    override = merged["confort"]["entry-abc"]
    assert override.temp == 21.5
    assert override.fan_rate == "B"
    assert merged["confort"]["salon"].temp == 20.0
