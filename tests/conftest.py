"""Fixtures for Dial-a-Story tests."""

from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.loader import Integration

from custom_components.dial_a_story.const import DOMAIN

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "dial_a_story"


@pytest.fixture(autouse=True)
async def register_integration(hass: HomeAssistant):
    """Register the dial_a_story integration with HA loader."""
    integration = Integration(
        hass,
        "custom_components.dial_a_story",
        COMPONENT_DIR,
        {
            "name": "Dial-a-Story",
            "domain": DOMAIN,
            "config_flow": True,
            "dependencies": ["webhook"],
            "codeowners": ["@brianegge"],
            "requirements": [],
            "documentation": "https://github.com/brianegge/dial-a-story",
            "iot_class": "cloud_push",
            "version": "1.0.2",
        },
    )

    hass.data.setdefault("integrations", {})[DOMAIN] = integration
