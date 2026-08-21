"""Small helpers shared by the client and tests."""

from __future__ import annotations

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


def module_url(host: str, path: str, *, https: bool = False) -> str:
    scheme = "https" if https else "http"
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{scheme}://{sanitize_host(host)}{path}"
