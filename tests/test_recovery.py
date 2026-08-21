from __future__ import annotations

from client import HealthStatus
from recovery import RecoveryAction, daily_counter_should_reset, decide_recovery


def test_no_action_when_healthy() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.OK,
            auto_reboot=True,
            consecutive_failures=5,
            failures_needed=3,
            soft_reboots_today=0,
            max_soft_reboots=6,
            has_hard_switch=True,
        )
        is RecoveryAction.NONE
    )


def test_waits_until_failure_threshold() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.ERROR_CODE,
            auto_reboot=True,
            consecutive_failures=2,
            failures_needed=3,
            soft_reboots_today=0,
            max_soft_reboots=6,
            has_hard_switch=False,
        )
        is RecoveryAction.NONE
    )


def test_soft_reboot_on_error_code() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.ERROR_CODE,
            auto_reboot=True,
            consecutive_failures=3,
            failures_needed=3,
            soft_reboots_today=0,
            max_soft_reboots=6,
            has_hard_switch=False,
        )
        is RecoveryAction.SOFT
    )


def test_unreachable_without_plug_waits() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.UNREACHABLE,
            auto_reboot=True,
            consecutive_failures=3,
            failures_needed=3,
            soft_reboots_today=0,
            max_soft_reboots=6,
            has_hard_switch=False,
        )
        is RecoveryAction.WAIT
    )


def test_unreachable_with_plug_hard_reboots() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.UNREACHABLE,
            auto_reboot=True,
            consecutive_failures=3,
            failures_needed=3,
            soft_reboots_today=0,
            max_soft_reboots=6,
            has_hard_switch=True,
        )
        is RecoveryAction.HARD
    )


def test_quota_escalates_to_hard_or_wait() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.ERROR_CODE,
            auto_reboot=True,
            consecutive_failures=3,
            failures_needed=3,
            soft_reboots_today=6,
            max_soft_reboots=6,
            has_hard_switch=True,
        )
        is RecoveryAction.HARD
    )
    assert (
        decide_recovery(
            status=HealthStatus.ERROR_CODE,
            auto_reboot=True,
            consecutive_failures=3,
            failures_needed=3,
            soft_reboots_today=6,
            max_soft_reboots=6,
            has_hard_switch=False,
        )
        is RecoveryAction.WAIT
    )


def test_auto_reboot_can_be_disabled() -> None:
    assert (
        decide_recovery(
            status=HealthStatus.ERROR_CODE,
            auto_reboot=False,
            consecutive_failures=10,
            failures_needed=3,
            soft_reboots_today=0,
            max_soft_reboots=6,
            has_hard_switch=True,
        )
        is RecoveryAction.NONE
    )


def test_daily_counter_reset() -> None:
    assert daily_counter_should_reset("2026-08-20", "2026-08-21")
    assert not daily_counter_should_reset("2026-08-21", "2026-08-21")
    assert daily_counter_should_reset(None, "2026-08-21")
