"""Fixtures for Shure SLX-D tests."""

from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.loader import Integration

from custom_components.shure_slxd.const import DOMAIN

COMPONENT_DIR = Path(__file__).parent.parent.parent / "custom_components" / "shure_slxd"


@pytest.fixture(autouse=True)
async def register_integration(hass: HomeAssistant):
    """Register the shure_slxd integration with HA loader."""
    integration = Integration(
        hass,
        "custom_components.shure_slxd",
        COMPONENT_DIR,
        {
            "name": "Shure SLX-D",
            "domain": DOMAIN,
            "config_flow": True,
            "dependencies": [],
            "codeowners": ["@brianegge"],
            "requirements": [],
            "documentation": "https://github.com/brianegge/homeassistant-dial-a-story",
            "iot_class": "local_polling",
            "version": "1.0.0",
        },
    )

    hass.data.setdefault("integrations", {})[DOMAIN] = integration
