"""Tests for time-of-day story framing."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from custom_components.dial_a_story import (
    BEDTIME_THEMES,
    DAYTIME_THEMES,
    STORY_THEMES,
    _backup_story,
    _daypart,
)

BEDTIME_SIGNOFF = "Sweet dreams, Chloe!"
DAYTIME_SIGNOFF = "Have a wonderful day, Chloe!"

# bedtime is 17:00-03:59, daytime is 04:00-16:59
BEDTIME_HOURS = [17, 20, 23, 0, 3]
DAYTIME_HOURS = [4, 8, 12, 16]

REQUIRED_KEYS = {
    "story_kind",
    "signoff",
    "theme",
    "arc",
    "voice",
    "greeting",
    "filler",
    "offer",
    "enough",
    "goodbye",
}


def _at(hour: int):
    """Freeze the clock at a given UTC hour."""
    return patch(
        "custom_components.dial_a_story.dt_util.utcnow",
        return_value=datetime(2026, 1, 1, hour, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize("hour", BEDTIME_HOURS)
def test_bedtime_hours_use_bedtime_signoff(hour: int) -> None:
    """Evening and small-hours calls get the bedtime sign-off."""
    with _at(hour):
        part = _daypart()
    assert part["signoff"] == BEDTIME_SIGNOFF
    assert "bedtime" in part["story_kind"]


@pytest.mark.parametrize("hour", DAYTIME_HOURS)
def test_daytime_hours_use_daytime_signoff(hour: int) -> None:
    """Daytime calls must not be told to go to sleep."""
    with _at(hour):
        part = _daypart()
    assert part["signoff"] == DAYTIME_SIGNOFF
    assert "bedtime" not in part["story_kind"]
    assert "sleep" not in part["goodbye"].lower()


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(8, "Good morning!"), (11, "Good morning!"), (12, "Hello!"), (16, "Hello!")],
)
def test_morning_greeting_only_before_noon(hour: int, expected: str) -> None:
    """The greeting says good morning only in the morning."""
    with _at(hour):
        assert _daypart()["greeting"].startswith(expected)


@pytest.mark.parametrize("hour", [*BEDTIME_HOURS, *DAYTIME_HOURS])
def test_daypart_always_has_every_key(hour: int) -> None:
    """Both branches must supply the same keys, or the call flow breaks."""
    with _at(hour):
        assert REQUIRED_KEYS <= set(_daypart())


@pytest.mark.parametrize("hour", BEDTIME_HOURS)
def test_bedtime_never_picks_a_daytime_theme(hour: int) -> None:
    """Splashing in puddles is the wrong energy at bedtime."""
    with _at(hour):
        themes = {_daypart()["theme"] for _ in range(200)}
    assert not themes & set(DAYTIME_THEMES)
    assert themes <= set(STORY_THEMES) | set(BEDTIME_THEMES)


@pytest.mark.parametrize("hour", DAYTIME_HOURS)
def test_daytime_never_picks_a_bedtime_theme(hour: int) -> None:
    """A story about the moon and stars lands badly at breakfast."""
    with _at(hour):
        themes = {_daypart()["theme"] for _ in range(200)}
    assert not themes & set(BEDTIME_THEMES)
    assert themes <= set(STORY_THEMES) | set(DAYTIME_THEMES)


def test_backup_story_keeps_bedtime_signoff() -> None:
    """Backup stories are written for bedtime and stay that way at night."""
    with _at(20):
        assert _backup_story().endswith(BEDTIME_SIGNOFF)


def test_backup_story_signoff_rewritten_for_daytime() -> None:
    """A 7am fallback must not wish her sweet dreams."""
    with _at(7):
        story = _backup_story()
    assert story.endswith(DAYTIME_SIGNOFF)
    assert BEDTIME_SIGNOFF not in story
