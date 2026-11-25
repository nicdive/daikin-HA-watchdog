from __future__ import annotations

from datetime import datetime, timedelta, timezone

from climate_rules import (
    desired_cool_mode,
    desired_heat_mode,
    is_night_hour,
    opening_is_blocking,
)


def test_heat_on_confort_day_home() -> None:
    assert (
        desired_heat_mode(
            salon=19.5,
            outdoor=16,
            presence_home=True,
            is_night=False,
            current_mode="off",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
        )
        == "confort"
    )


def test_heat_nuit() -> None:
    assert (
        desired_heat_mode(
            salon=19.5,
            outdoor=10,
            presence_home=True,
            is_night=True,
            current_mode="off",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
        )
        == "nuit"
    )


def test_heat_eco_away() -> None:
    assert (
        desired_heat_mode(
            salon=18,
            outdoor=10,
            presence_home=False,
            is_night=False,
            current_mode="off",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
        )
        == "eco"
    )


def test_heat_off_outdoor_warm() -> None:
    assert (
        desired_heat_mode(
            salon=22,
            outdoor=20,
            presence_home=True,
            is_night=False,
            current_mode="confort",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
        )
        == "off"
    )


def test_heat_deadband_keeps_current() -> None:
    assert (
        desired_heat_mode(
            salon=22,
            outdoor=16,
            presence_home=True,
            is_night=False,
            current_mode="confort",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
        )
        == "confort"
    )


def test_heat_deadband_latched_off_stays_off() -> None:
    assert (
        desired_heat_mode(
            salon=22,
            outdoor=16,
            presence_home=True,
            is_night=False,
            current_mode="off",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
            off_latched=True,
        )
        == "off"
    )


def test_heat_deadband_unlatched_off_resumes_after_reload() -> None:
    """After reload, mode may be off without OFF-threshold latch → resume heat."""
    assert (
        desired_heat_mode(
            salon=21.8,
            outdoor=16.5,
            presence_home=False,
            is_night=True,
            current_mode="off",
            heat_on_salon_below=21,
            heat_on_outdoor_below=14,
            heat_off_salon_above=24,
            heat_off_outdoor_above=19,
            off_latched=False,
        )
        == "eco"
    )


def test_cool_jour_and_off() -> None:
    assert (
        desired_cool_mode(
            salon=29,
            outdoor=31,
            presence_home=True,
            is_night=False,
            current_mode="off",
            cool_on_salon_above=28.4,
            cool_on_outdoor_above=30,
            cool_off_outdoor_below=23,
        )
        == "jour"
    )
    assert (
        desired_cool_mode(
            salon=29,
            outdoor=22,
            presence_home=True,
            is_night=False,
            current_mode="jour",
            cool_on_salon_above=28.4,
            cool_on_outdoor_above=30,
            cool_off_outdoor_below=23,
        )
        == "off"
    )


def test_night_window_21_to_6() -> None:
    assert is_night_hour(20, night_start_hour=21, night_end_hour=6) is False
    assert is_night_hour(21, night_start_hour=21, night_end_hour=6) is True
    assert is_night_hour(23, night_start_hour=21, night_end_hour=6) is True
    assert is_night_hour(0, night_start_hour=21, night_end_hour=6) is True
    assert is_night_hour(5, night_start_hour=21, night_end_hour=6) is True
    assert is_night_hour(6, night_start_hour=21, night_end_hour=6) is False
    assert is_night_hour(12, night_start_hour=21, night_end_hour=6) is False


def test_opening_delay() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    blocked, since = opening_is_blocking(
        is_open=True, open_since=None, now=now, delay_seconds=300
    )
    assert blocked is False
    assert since == now

    blocked, since = opening_is_blocking(
        is_open=True,
        open_since=now - timedelta(seconds=301),
        now=now,
        delay_seconds=300,
    )
    assert blocked is True

    blocked, since = opening_is_blocking(
        is_open=False, open_since=now, now=now, delay_seconds=300
    )
    assert blocked is False
    assert since is None
