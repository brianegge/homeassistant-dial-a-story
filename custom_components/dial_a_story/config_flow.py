"""Config flow for Dial-a-Story integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ELEVENLABS_API_KEY,
    CONF_STORY_LENGTH,
    CONF_TELNYX_API_KEY,
    CONF_VOICE_PREFERENCE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _validate_telnyx_api_key(hass, api_key: str) -> bool:
    """Validate the Telnyx API key by listing phone numbers."""
    session = async_get_clientsession(hass)
    try:
        response = await session.get(
            "https://api.telnyx.com/v2/phone_numbers?page[size]=1",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        if response.status == 401:
            return False
        if response.status == 403:
            return False
        return response.status == 200
    except Exception:
        raise


class DialAStoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dial-a-Story."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Prevent duplicate entries
            self._async_abort_entries_match(
                {CONF_TELNYX_API_KEY: user_input[CONF_TELNYX_API_KEY]}
            )

            # Test the Telnyx API key
            try:
                valid = await _validate_telnyx_api_key(
                    self.hass, user_input[CONF_TELNYX_API_KEY]
                )
                if not valid:
                    errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Error connecting to Telnyx API")
                errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="Dial-a-Story",
                    data={
                        CONF_TELNYX_API_KEY: user_input[CONF_TELNYX_API_KEY],
                        CONF_ELEVENLABS_API_KEY: user_input.get(
                            CONF_ELEVENLABS_API_KEY, ""
                        ),
                        CONF_STORY_LENGTH: user_input.get(
                            CONF_STORY_LENGTH, "medium"
                        ),
                        CONF_VOICE_PREFERENCE: user_input.get(
                            CONF_VOICE_PREFERENCE, "female"
                        ),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TELNYX_API_KEY): str,
                    vol.Optional(CONF_ELEVENLABS_API_KEY): str,
                    vol.Optional(CONF_STORY_LENGTH, default="medium"): vol.In(
                        ["short", "medium", "long"]
                    ),
                    vol.Optional(CONF_VOICE_PREFERENCE, default="female"): vol.In(
                        ["male", "female"]
                    ),
                }
            ),
            errors=errors,
        )
