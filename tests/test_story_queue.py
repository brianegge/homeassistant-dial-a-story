"""Tests for Dial-a-Story story queue (set_story / clear_story services)."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.dial_a_story import DialAStoryData, _CallHandler
from custom_components.dial_a_story.const import DOMAIN


@pytest.fixture
def runtime_data() -> DialAStoryData:
    """Create runtime data with defaults."""
    return DialAStoryData(
        telnyx_api_key="test_key",
        elevenlabs_api_key=None,
        story_length="medium",
        voice_preference="female",
    )


async def test_generate_story_uses_queued_story(hass: HomeAssistant, runtime_data: DialAStoryData) -> None:
    """Test that _generate_story returns queued story and consumes it."""
    runtime_data.queued_stories = ["My custom story about a dragon."]

    # Register a mock config entry so _get_runtime_data works
    entry = AsyncMock()
    entry.runtime_data = runtime_data
    entry.domain = DOMAIN
    entry.entry_id = "test_entry"
    hass.data.setdefault("integrations", {})

    with patch(
        "custom_components.dial_a_story._get_runtime_data",
        return_value=runtime_data,
    ):
        handler = _CallHandler(hass)
        story = await handler._generate_story()

    assert story == "My custom story about a dragon."
    assert runtime_data.queued_stories == []


async def test_generate_story_falls_through_when_no_queue(
    hass: HomeAssistant, runtime_data: DialAStoryData
) -> None:
    """Test that _generate_story uses AI/backup when no queued story."""
    assert runtime_data.queued_stories == []

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_generate_story_ai_task",
            return_value="AI generated story",
        ),
    ):
        handler = _CallHandler(hass)
        story = await handler._generate_story()

    assert story == "AI generated story"


async def test_queued_story_consumed_only_once(hass: HomeAssistant, runtime_data: DialAStoryData) -> None:
    """Test that queued story is consumed after first use."""
    runtime_data.queued_stories = ["One-time story."]

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_generate_story_ai_task",
            return_value="AI story",
        ),
    ):
        handler = _CallHandler(hass)

        first = await handler._generate_story()
        assert first == "One-time story."

        second = await handler._generate_story()
        assert second == "AI story"


async def test_queued_stories_are_returned_in_order(hass: HomeAssistant, runtime_data: DialAStoryData) -> None:
    """Test that multiple queued stories are consumed FIFO."""
    runtime_data.queued_stories = ["First story.", "Second story.", "Third story."]

    with (
        patch(
            "custom_components.dial_a_story._get_runtime_data",
            return_value=runtime_data,
        ),
        patch.object(
            _CallHandler,
            "_generate_story_ai_task",
            return_value="AI story",
        ),
    ):
        handler = _CallHandler(hass)

        assert await handler._generate_story() == "First story."
        assert await handler._generate_story() == "Second story."
        assert len(runtime_data.queued_stories) == 1

        assert await handler._generate_story() == "Third story."
        assert runtime_data.queued_stories == []

        # queue drained, falls through to generation
        assert await handler._generate_story() == "AI story"
