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
    if "://" in raw:
        parsed = urlsplit(raw)
        raw = (parsed.netloc or parsed.path or "").strip().strip("/")
    if _IPV4.fullmatch(raw):
        return True
    if raw.startswith("[") and "]" in raw:
        raw = raw[1 : raw.index("]")]
    if "%" in raw:
        raw = raw.split("%", 1)[0]
    if ":" in raw and raw.count(":") == 1:
        host_part, _, port = raw.partition(":")
        if port.isdigit():
            raw = host_part
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


def daikin_entry_display_name(hass: Any, entry: Any) -> str:
    """Human label for a Daikin AC config entry (never the bare IP if avoidable)."""
    from homeassistant.helpers import area_registry as ar
    from homeassistant.helpers import device_registry as dr
    from homeassistant.helpers import entity_registry as er

    host = str((getattr(entry, "data", {}) or {}).get("host") or "")
    title = str(getattr(entry, "title", "") or "")
    entry_id = str(getattr(entry, "entry_id", "") or "")

    candidates: list[str] = []
    area_name: str | None = None

    try:
        ent_reg = er.async_get(hass)
        for ent in er.async_entries_for_config_entry(ent_reg, entry_id):
            if ent.domain != "climate":
                continue
            state = hass.states.get(ent.entity_id)
            if state is not None and state.name:
                candidates.append(state.name)
            if ent.name:
                candidates.append(ent.name)
            if ent.original_name:
                candidates.append(ent.original_name)
            if ent.area_id:
                area = ar.async_get(hass).async_get_area(ent.area_id)
                if area:
                    area_name = area.name
            break
    except Exception:  # noqa: BLE001
        pass

    try:
        dev_reg = dr.async_get(hass)
        devices = list(dr.async_entries_for_config_entry(dev_reg, entry_id))
        devices.sort(
            key=lambda device: (
                0 if device.name_by_user else 1,
                0 if device.area_id else 1,
                device.name or "",
            )
        )
        if devices:
            device = devices[0]
            if device.name_by_user:
                candidates.insert(0, device.name_by_user)
            if device.name:
                candidates.append(device.name)
            if not area_name and device.area_id:
                area = ar.async_get(hass).async_get_area(device.area_id)
                if area:
                    area_name = area.name
    except Exception:  # noqa: BLE001
        pass

    if title and not looks_like_host(title):
        candidates.append(title)

    # Known eedomus room keys matched by IP / title hints.
    try:
        from .climate_defaults import DEVICE_HOSTS, match_device_key

        key = match_device_key(host, title) or match_device_key(
            host, candidates[0] if candidates else None
        )
        pretty = {
            "bureau": "Bureau",
            "clara": "Chambre Clara",
            "invites": "Chambre invités",
            "louis": "Chambre Louis",
            "cuisine": "Cuisine",
            "salon": "Salon",
            "suite": "Suite parentale",
        }
        if key and key in pretty:
            candidates.append(pretty[key])
        # Reverse host map
        for slug, known_host in DEVICE_HOSTS.items():
            if host == known_host and slug in pretty:
                candidates.append(pretty[slug])
    except Exception:  # noqa: BLE001
        pass

    name = next(
        (candidate for candidate in candidates if candidate and not looks_like_host(candidate)),
        None,
    )
    if not name:
        name = title if title and not looks_like_host(title) else (area_name or host or entry_id)
    return format_device_label(name, area_name)


def module_url(host: str, path: str, *, https: bool = False) -> str:
    scheme = "https" if https else "http"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{sanitize_host(host)}{path}"
