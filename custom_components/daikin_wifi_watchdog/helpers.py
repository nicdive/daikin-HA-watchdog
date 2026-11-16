"""Small helpers shared by the client and tests."""

from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def reboot_exception_is_expected(exc: BaseException) -> bool:
    """Daikin modules often drop the TCP connection (or time out) while rebooting."""
    if isinstance(exc, TimeoutError):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name or "disconnect" in name:
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in ("timeout", "connection", "connect", "disconnected", "closed")
    )


def sanitize_host(host: str) -> str:
    """Normalize a Daikin host so we can safely build http(s) URLs."""
    raw = (host or "").strip()
    if not raw:
        raise ValueError("empty host")
    if "://" in raw:
        parsed = urlsplit(raw)
        raw = parsed.netloc or parsed.path
    raw = raw.strip().strip("/")
    if raw.startswith("[") and "]" in raw:
        return raw
    # IPv6 literals must be bracketed. A port is only valid as [ipv6]:port.
    if raw.count(":") > 1:
        return f"[{raw}]"
    return raw


_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?$")


def looks_like_host(value: str | None) -> bool:
    """True when a label is an IP address, not a human device name."""
    raw = (value or "").strip()
    if not raw:
        return True
    if _IPV4.fullmatch(raw):
        return True
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    if "%" in raw:
        raw = raw.split("%", 1)[0]
    try:
        ipaddress.ip_address(raw)
        return True
    except ValueError:
        return False


_UNDERSCORE_VER = re.compile(r"^\d+(?:_\d+)+$")


def integration_version() -> str:
    """Version from manifest.json — the value Home Assistant should show."""
    manifest = Path(__file__).with_name("manifest.json")
    return str(json.loads(manifest.read_text(encoding="utf-8"))["version"])


def format_adapter_version(value: Any) -> str | None:
    """Turn Daikin firmware strings like 1_2_54 into 1.2.54."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _UNDERSCORE_VER.fullmatch(text):
        return text.replace("_", ".")
    return text


def format_device_label(name: str, area: str | None = None) -> str:
    """Build a notification label like 'Clim salon (Chambre)'."""
    label = (name or "").strip() or "Daikin"
    area_name = (area or "").strip()
    if area_name and area_name.casefold() not in label.casefold():
        return f"{label} ({area_name})"
    return label


def module_url(host: str, path: str, *, https: bool = False) -> str:
    scheme = "https" if https else "http"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{sanitize_host(host)}{path}"
