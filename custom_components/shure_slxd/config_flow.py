"""Config flow for Shure SLX-D integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult

from .client import ShureClient
from .const import CONF_HOST, CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class ShureSlxdConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Shure SLX-D."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            num_channels = user_input.get(CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS)

            # Prevent duplicate entries for the same host
            self._async_abort_entries_match({CONF_HOST: host})

            # Test connection to the receiver
            client = ShureClient(host)
            try:
                device_info = await client.test_connection()
                model = device_info.get("model", "SLXD4")
                device_id = device_info.get("device_id", host)
            except Exception:
                _LOGGER.exception("Error connecting to Shure receiver at %s", host)
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Shure {model}",
                    data={
                        CONF_HOST: host,
                        CONF_NUM_CHANNELS: num_channels,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_NUM_CHANNELS, default=DEFAULT_NUM_CHANNELS): vol.In([1, 2, 4]),
                }
            ),
            errors=errors,
        )
