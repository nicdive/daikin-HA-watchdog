from __future__ import annotations

from climate_defaults import (
    DEFAULT_COOL_PRESETS,
    DEFAULT_HEAT_PRESETS,
    DEVICE_HOSTS,
    DeviceSetpoint,
    match_device_key,
    presets_from_dict,
    presets_to_dict,
    serialize_default_heat_presets,
)


def test_all_devices_present_in_heat_presets() -> None:
    for mode, devices in DEFAULT_HEAT_PRESETS.items():
        assert set(devices) == set(DEVICE_HOSTS)
        for key, sp in devices.items():
            assert isinstance(sp, DeviceSetpoint)
            if mode == "off":
                assert sp.power is False
            if mode == "confort" and key == "salon":
                assert sp.power is True
                assert sp.temp == 20
                assert sp.mode == "4"


def test_nuit_heat_quiet_bedrooms() -> None:
    nuit = DEFAULT_HEAT_PRESETS["nuit"]
    assert nuit["clara"].fan_rate == "B"
    assert nuit["louis"].fan_rate == "B"
    assert nuit["suite"].fan_rate == "B"
    assert nuit["invites"].power is False
    assert nuit["bureau"].temp == 17
    assert nuit["bureau"].fan_rate == "A"


def test_cool_presets() -> None:
    jour = DEFAULT_COOL_PRESETS["jour"]
    assert jour["salon"].temp == 27
    assert jour["invites"].temp == 29
    nuit = DEFAULT_COOL_PRESETS["nuit"]
    assert nuit["cuisine"].power is False
    assert nuit["salon"].power is False
    assert nuit["clara"].fan_rate == "B"
    assert nuit["suite"].temp == 26
    dry = DEFAULT_COOL_PRESETS["dry"]
    assert all(sp.mode == "2" and sp.power for sp in dry.values())


def test_match_device_key_by_host_and_title() -> None:
    assert match_device_key("192.168.23.153", None) == "salon"
    assert match_device_key("10.0.0.1", "Clim Salon") == "salon"
    assert match_device_key("10.0.0.1", "Chambre Clara") == "clara"
    assert match_device_key("10.0.0.1", "Suite parentale") == "suite"
    assert match_device_key("10.0.0.1", "Invités") == "invites"
    assert match_device_key("10.0.0.1", "Unknown") is None


def test_presets_merge_override() -> None:
    raw = serialize_default_heat_presets()
    raw["confort"]["salon"]["temp"] = 21.0
    merged = presets_from_dict(raw, DEFAULT_HEAT_PRESETS)
    assert merged["confort"]["salon"].temp == 21.0
    assert merged["confort"]["bureau"].temp == 18
    roundtrip = presets_to_dict(merged)
    assert roundtrip["confort"]["salon"]["temp"] == 21.0
