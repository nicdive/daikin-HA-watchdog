"""Default heating/cooling presets and AUTO thresholds (eedomus migration)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any

# Stable host keys from the original eedomus setup. Matched at runtime by IP
# first, then by fuzzy title (bureau, clara, …).
DEVICE_HOSTS: dict[str, str] = {
    "bureau": "192.168.23.138",
    "clara": "192.168.23.140",
    "invites": "192.168.23.139",
    "louis": "192.168.23.143",
    "cuisine": "192.168.23.151",
    "salon": "192.168.23.153",
    "suite": "192.168.23.136",
}

DEVICE_TITLE_HINTS: dict[str, tuple[str, ...]] = {
    "bureau": ("bureau",),
    "clara": ("clara",),
    "invites": ("invite", "invité", "invites", "invités"),
    "louis": ("louis",),
    "cuisine": ("cuisine",),
    "salon": ("salon",),
    "suite": ("suite", "parentale", "parents"),
}

HEAT_MODES = ("off", "hors_gel", "confort", "eco", "nuit")
COOL_MODES = ("off", "jour", "nuit", "eco", "dry")

HEAT_MODE_LABELS = {
    "off": "Off",
    "hors_gel": "Hors-gel",
    "confort": "Confort",
    "eco": "Eco",
    "nuit": "Nuit",
}
COOL_MODE_LABELS = {
    "off": "Off",
    "jour": "Jour",
    "nuit": "Nuit",
    "eco": "Eco",
    "dry": "Déshumidification",
}

DAIKIN_MODE_HEAT = "4"
DAIKIN_MODE_COOL = "3"
DAIKIN_MODE_DRY = "2"

FAN_AUTO = "A"
FAN_QUIET = "B"
DIR_STOPPED = "0"
DIR_VERTICAL = "1"
DIR_HORIZONTAL = "2"
DIR_BOTH = "3"

# Values stored in presets / sent to Daikin local API.
FAN_RATE_OPTIONS = ("A", "B", "3", "4", "5", "6", "7")
FAN_DIR_OPTIONS = (DIR_STOPPED, DIR_VERTICAL, DIR_HORIZONTAL, DIR_BOTH)


@dataclass(slots=True, frozen=True)
class DeviceSetpoint:
    """One unit target inside a scene/preset."""

    power: bool
    temp: float | None = None
    mode: str = DAIKIN_MODE_HEAT
    fan_rate: str = FAN_AUTO
    fan_dir: str = DIR_BOTH

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DeviceSetpoint:
        if not data:
            return OFF
        return cls(
            power=bool(data.get("power", False)),
            temp=_float_or_none(data.get("temp")),
            mode=str(data.get("mode") or DAIKIN_MODE_HEAT),
            fan_rate=str(data.get("fan_rate") or FAN_AUTO),
            fan_dir=str(data.get("fan_dir") or DIR_BOTH),
        )


OFF = DeviceSetpoint(power=False)


def _heat(temp: float, *, quiet: bool = False) -> DeviceSetpoint:
    return DeviceSetpoint(
        power=True,
        temp=temp,
        mode=DAIKIN_MODE_HEAT,
        fan_rate=FAN_QUIET if quiet else FAN_AUTO,
        fan_dir=DIR_STOPPED if quiet else DIR_BOTH,
    )


def _cool(temp: float, *, quiet: bool = False) -> DeviceSetpoint:
    return DeviceSetpoint(
        power=True,
        temp=temp,
        mode=DAIKIN_MODE_COOL,
        fan_rate=FAN_QUIET if quiet else FAN_AUTO,
        fan_dir=DIR_STOPPED if quiet else DIR_BOTH,
    )


DRY = DeviceSetpoint(
    power=True,
    temp=None,
    mode=DAIKIN_MODE_DRY,
    fan_rate=FAN_AUTO,
    fan_dir=DIR_BOTH,
)

# Heating scenes — temperatures from eedomus macros.
DEFAULT_HEAT_PRESETS: dict[str, dict[str, DeviceSetpoint]] = {
    "off": {key: OFF for key in DEVICE_HOSTS},
    "hors_gel": {
        "bureau": _heat(15),
        "clara": _heat(15),
        "invites": OFF,
        "louis": _heat(15),
        "cuisine": _heat(15),
        "salon": _heat(15),
        "suite": _heat(15),
    },
    "confort": {
        "bureau": _heat(18),
        "clara": _heat(18),
        "invites": _heat(15),
        "louis": _heat(18),
        "cuisine": _heat(19),
        "salon": _heat(20),
        "suite": _heat(19),
    },
    "eco": {
        "bureau": _heat(16),
        "clara": _heat(16),
        "invites": OFF,
        "louis": _heat(16),
        "cuisine": _heat(17),
        "salon": _heat(18),
        "suite": _heat(17),
    },
    "nuit": {
        "bureau": _heat(17),
        "clara": _heat(18, quiet=True),
        "invites": OFF,
        "louis": _heat(18, quiet=True),
        "cuisine": _heat(18),
        "salon": _heat(18),
        "suite": _heat(19, quiet=True),
    },
}

# Cooling scenes — temperatures from eedomus macros.
DEFAULT_COOL_PRESETS: dict[str, dict[str, DeviceSetpoint]] = {
    "off": {key: OFF for key in DEVICE_HOSTS},
    "jour": {
        "bureau": _cool(27),
        "clara": _cool(27),
        "invites": _cool(29),
        "louis": _cool(27),
        "cuisine": _cool(27),
        "salon": _cool(27),
        "suite": _cool(27),
    },
    "nuit": {
        "bureau": _cool(27, quiet=True),
        "clara": _cool(27, quiet=True),
        "invites": _cool(29),
        "louis": _cool(27, quiet=True),
        "cuisine": OFF,
        "salon": OFF,
        "suite": _cool(26),
    },
    "eco": {
        "bureau": _cool(29),
        "clara": _cool(29),
        "invites": _cool(29),
        "louis": _cool(29),
        "cuisine": _cool(29),
        "salon": _cool(29),
        "suite": _cool(29),
    },
    "dry": {key: DRY for key in DEVICE_HOSTS},
}

# AUTO thresholds (°C) and opening delay.
DEFAULT_HEAT_ON_SALON_BELOW = 21.0
DEFAULT_HEAT_ON_OUTDOOR_BELOW = 14.0
DEFAULT_HEAT_OFF_SALON_ABOVE = 24.0
DEFAULT_HEAT_OFF_OUTDOOR_ABOVE = 19.0
DEFAULT_COOL_ON_SALON_ABOVE = 28.4
DEFAULT_COOL_ON_OUTDOOR_ABOVE = 30.0
DEFAULT_COOL_OFF_OUTDOOR_BELOW = 23.0
DEFAULT_OPENING_DELAY_SECONDS = 300


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def presets_to_dict(
    presets: dict[str, dict[str, DeviceSetpoint]],
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        mode: {device: sp.to_dict() for device, sp in devices.items()}
        for mode, devices in presets.items()
    }


def presets_from_dict(
    raw: dict[str, Any] | None,
    defaults: dict[str, dict[str, DeviceSetpoint]],
) -> dict[str, dict[str, DeviceSetpoint]]:
    """Merge user overrides onto defaults (device-key based)."""
    merged = deepcopy(defaults)
    if not raw:
        return merged
    for mode, devices in raw.items():
        if mode not in merged or not isinstance(devices, dict):
            continue
        for device_key, payload in devices.items():
            if device_key not in merged[mode]:
                # Allow entry_id / host overrides stored by the options flow.
                merged[mode][device_key] = DeviceSetpoint.from_dict(payload)
            else:
                merged[mode][device_key] = DeviceSetpoint.from_dict(payload)
    return merged


def match_device_key(host: str | None, title: str | None) -> str | None:
    """Map a live Daikin module to a default device key."""
    host_norm = (host or "").strip()
    for key, known_host in DEVICE_HOSTS.items():
        if host_norm == known_host:
            return key
    title_l = (title or "").casefold()
    if not title_l:
        return None
    for key, hints in DEVICE_TITLE_HINTS.items():
        if any(hint in title_l for hint in hints):
            return key
    return None


def serialize_default_heat_presets() -> dict[str, dict[str, dict[str, Any]]]:
    return presets_to_dict(DEFAULT_HEAT_PRESETS)


def serialize_default_cool_presets() -> dict[str, dict[str, dict[str, Any]]]:
    return presets_to_dict(DEFAULT_COOL_PRESETS)
