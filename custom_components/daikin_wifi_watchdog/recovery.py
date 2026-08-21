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
    """Choose the next recovery action after a failed health check."""
    if status in {HealthStatus.OK, HealthStatus.DISABLED, HealthStatus.REBOOTING}:
        return RecoveryAction.NONE
    if not auto_reboot or consecutive_failures < failures_needed:
        return RecoveryAction.NONE
    if status is HealthStatus.UNREACHABLE:
        return RecoveryAction.HARD if has_hard_switch else RecoveryAction.WAIT
    if soft_reboots_today >= max_soft_reboots:
        return RecoveryAction.HARD if has_hard_switch else RecoveryAction.WAIT
    return RecoveryAction.SOFT


def daily_counter_should_reset(stored_day: str | None, today: str) -> bool:
    return stored_day != today
