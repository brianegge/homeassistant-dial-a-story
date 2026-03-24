"""Shure SLX-D wireless microphone receiver integration for Home Assistant.

Connects to Shure SLXD4/SLXD4D receivers over TCP (port 2202) using the
Shure command-string protocol to expose battery level, RF signal strength,
and other channel metrics as sensors.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .client import ShureClient
from .const import CONF_HOST, CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS, DEFAULT_PORT, DOMAIN
from .coordinator import ShureCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Shure SLX-D from a config entry."""
    host = entry.data[CONF_HOST]
    num_channels = entry.data.get(CONF_NUM_CHANNELS, DEFAULT_NUM_CHANNELS)

    client = ShureClient(host, DEFAULT_PORT)
    try:
        await client.connect()
    except Exception as err:
        raise ConfigEntryNotReady(f"Cannot connect to Shure receiver at {host}: {err}") from err

    coordinator = ShureCoordinator(hass, client, num_channels)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Shure SLX-D integration initialized for %s", host)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Shure SLX-D config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: ShureCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.client.disconnect()
    return unload_ok
