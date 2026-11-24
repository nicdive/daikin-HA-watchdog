"""Pure AUTO decision helpers (no Home Assistant import)."""

from __future__ import annotations

from datetime import datetime, timedelta


def desired_heat_mode(
    *,
    salon: float | None,
    outdoor: float | None,
    presence_home: bool | None,
    is_night: bool,
    current_mode: str,
    heat_on_salon_below: float,
    heat_on_outdoor_below: float,
    heat_off_salon_above: float,
    heat_off_outdoor_above: float,
) -> str | None:
    """Return target heat mode, or None when sensors are missing and idle."""
    should_off = False
    if outdoor is not None and outdoor > heat_off_outdoor_above:
        should_off = True
    if salon is not None and salon > heat_off_salon_above:
        should_off = True
    if should_off:
        return "off"

    should_on = False
    if salon is not None and salon < heat_on_salon_below:
        should_on = True
    if outdoor is not None and outdoor < heat_on_outdoor_below:
        should_on = True
    if not should_on:
        if salon is None and outdoor is None:
            return None
        if current_mode != "off":
            should_on = True
        else:
            return "off"

    if presence_home is False:
        return "eco"
    if is_night:
        return "nuit"
    return "confort"


def desired_cool_mode(
    *,
    salon: float | None,
    outdoor: float | None,
    presence_home: bool | None,
    is_night: bool,
    current_mode: str,
    cool_on_salon_above: float,
    cool_on_outdoor_above: float,
    cool_off_outdoor_below: float,
) -> str | None:
    """Return target cool mode, or None when sensors are missing and idle."""
    if outdoor is not None and outdoor < cool_off_outdoor_below:
        return "off"

    should_on = False
    if salon is not None and salon > cool_on_salon_above:
        should_on = True
    if outdoor is not None and outdoor > cool_on_outdoor_above:
        should_on = True
    if not should_on:
        if salon is None and outdoor is None:
            return None
        if current_mode not in ("off", "dry"):
            should_on = True
        else:
            return "off"

    if presence_home is False:
        return "eco"
    if is_night:
        return "nuit"
    return "jour"


def is_night_hour(
    hour: int,
    *,
    night_start_hour: int = 21,
    night_end_hour: int = 6,
) -> bool:
    """True during the night window, e.g. 21:00–06:00 local."""
    start = int(night_start_hour) % 24
    end = int(night_end_hour) % 24
    hour = int(hour) % 24
    if start == end:
        return False
    if start > end:
        # Wraps midnight: 21 → 6
        return hour >= start or hour < end
    return start <= hour < end


def opening_is_blocking(
    *,
    is_open: bool,
    open_since: datetime | None,
    now: datetime,
    delay_seconds: int,
) -> tuple[bool, datetime | None]:
    """Return (blocked, updated_open_since)."""
    if not is_open:
        return False, None
    if open_since is None:
        return False, now
    blocked = (now - open_since) >= timedelta(seconds=max(0, delay_seconds))
    return blocked, open_since
