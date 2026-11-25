"""Pure recovery decisions — kept free of Home Assistant imports for unit tests."""

from __future__ import annotations

from enum import StrEnum

try:
    from .client import HealthStatus
except ImportError:  # unit tests
    from client import HealthStatus


class RecoveryAction(StrEnum):
    NONE = "none"
    SOFT = "soft"
    HARD = "hard"
    WAIT = "wait"


def decide_recovery(
    *,
    status: HealthStatus,
    auto_reboot: bool,
    consecutive_failures: int,
    failures_needed: int,
    soft_reboots_today: int,
    max_soft_reboots: int,
    has_hard_switch: bool,
) -> RecoveryAction:
    """Choose the next recovery action after a failed health check.

    - ``error_code`` / ``bad_response``: soft reboot, then hard/wait after quota.
    - ``unreachable`` with a hard-reboot plug: hard reboot (local API is dead).
    - ``unreachable`` without a plug: still try soft reboot (flaky WiFi modules
      often accept ``/common/reboot`` even when ``basic_info`` times out), then
      wait after the daily soft quota is exhausted.
    """
    if status in {HealthStatus.OK, HealthStatus.DISABLED, HealthStatus.REBOOTING}:
        return RecoveryAction.NONE
    if not auto_reboot or consecutive_failures < failures_needed:
        return RecoveryAction.NONE

    quota_exhausted = soft_reboots_today >= max_soft_reboots

    if status is HealthStatus.UNREACHABLE:
        if has_hard_switch:
            # Prefer power-cycle when the module does not answer at all.
            return RecoveryAction.HARD
        if quota_exhausted:
            return RecoveryAction.WAIT
        return RecoveryAction.SOFT

    if quota_exhausted:
        return RecoveryAction.HARD if has_hard_switch else RecoveryAction.WAIT
    return RecoveryAction.SOFT


def daily_counter_should_reset(stored_day: str | None, today: str) -> bool:
    return stored_day != today
