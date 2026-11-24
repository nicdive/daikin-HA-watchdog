"""Auto-register the Programmation Clim Lovelace dashboard."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.start import async_at_started

_LOGGER = logging.getLogger(__name__)

DASHBOARD_URL_PATH = "daikin-programmation"
DASHBOARD_TITLE = "Programmation Clim"
DASHBOARD_ICON = "mdi:calendar-clock"
_YAML_FILE = Path(__file__).with_name("dashboards") / "programmation.yaml"


def schedule_dashboard_install(hass: HomeAssistant) -> None:
    """Install the sidebar dashboard once Home Assistant has started."""

    async def _at_start(hass_started: HomeAssistant) -> None:
        await async_setup_lovelace_dashboard(hass_started)

    async_at_started(hass, _at_start)


async def async_setup_lovelace_dashboard(hass: HomeAssistant) -> None:
    """Register / refresh the YAML dashboard shipped with this integration."""
    if not await _wait_for_lovelace(hass):
        _LOGGER.debug("Lovelace unavailable — skip Programmation Clim dashboard")
        return

    try:
        from homeassistant.components import frontend
        from homeassistant.components.lovelace import dashboard as lovelace_dashboard
        from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_YAML
    except ImportError:  # pragma: no cover - extremely old HA
        _LOGGER.debug("Lovelace APIs missing — skip dashboard install")
        return

    if not _YAML_FILE.is_file():
        _LOGGER.warning("Dashboard YAML missing at %s", _YAML_FILE)
        return

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("LOVELACE_DATA not ready — skip dashboard install")
        return

    conf: dict[str, Any] = {
        "mode": MODE_YAML,
        "title": DASHBOARD_TITLE,
        "icon": DASHBOARD_ICON,
        "show_in_sidebar": True,
        "require_admin": False,
        "filename": str(_YAML_FILE),
    }

    existing = lovelace_data.dashboards.get(DASHBOARD_URL_PATH)
    # Never clobber a user-built storage dashboard on the same path.
    if existing is not None and existing.__class__.__name__ == "LovelaceStorage":
        _LOGGER.info(
            "Dashboard path %s already used in storage mode — leaving it alone",
            DASHBOARD_URL_PATH,
        )
        return

    lovelace_data.dashboards[DASHBOARD_URL_PATH] = lovelace_dashboard.LovelaceYAML(
        hass, DASHBOARD_URL_PATH, conf
    )
    lovelace_data.yaml_dashboards[DASHBOARD_URL_PATH] = conf

    update = _panel_exists(frontend, hass, DASHBOARD_URL_PATH)
    try:
        frontend.async_register_built_in_panel(
            hass,
            "lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon=DASHBOARD_ICON,
            frontend_url_path=DASHBOARD_URL_PATH,
            config={"mode": MODE_YAML},
            require_admin=False,
            show_in_sidebar=True,
            update=update,
        )
    except TypeError:
        # Older HA without show_in_sidebar / update kwargs.
        frontend.async_register_built_in_panel(
            hass,
            "lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon=DASHBOARD_ICON,
            frontend_url_path=DASHBOARD_URL_PATH,
            config={"mode": MODE_YAML},
            require_admin=False,
        )
    except ValueError:
        _LOGGER.debug("Panel %s already registered", DASHBOARD_URL_PATH)
        return

    _LOGGER.info(
        "Dashboard « %s » available in the sidebar (/%s)",
        DASHBOARD_TITLE,
        DASHBOARD_URL_PATH,
    )


def _panel_exists(frontend: Any, hass: HomeAssistant, url_path: str) -> bool:
    """Compat wrapper — async_panel_exists is recent."""
    helper = getattr(frontend, "async_panel_exists", None)
    if helper is not None:
        return bool(helper(hass, url_path))
    return url_path in hass.data.get("frontend_panels", {})


async def _wait_for_lovelace(hass: HomeAssistant, *, timeout: float = 60.0) -> bool:
    """Wait until the lovelace integration has populated hass.data."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
    except ImportError:
        return False

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if "lovelace" in hass.config.components and hass.data.get(LOVELACE_DATA) is not None:
            return True
        await asyncio.sleep(0.5)
    return hass.data.get(LOVELACE_DATA) is not None
