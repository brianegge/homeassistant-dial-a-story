"""Data update coordinator for Shure SLX-D receivers."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import ReceiverData, ShureClient
from .const import SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class ShureCoordinator(DataUpdateCoordinator[ReceiverData]):
    """Coordinator that polls a Shure SLX-D receiver over TCP."""

    def __init__(self, hass: HomeAssistant, client: ShureClient, num_channels: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Shure SLXD ({client.host})",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self.num_channels = num_channels

    async def _async_update_data(self) -> ReceiverData:
        """Poll the receiver for current data."""
        try:
            if not self.client._writer:
                await self.client.connect()
            return await self.client.poll_all(self.num_channels)
        except Exception as err:
            # Reconnect on next poll
            await self.client.disconnect()
            raise UpdateFailed(f"Error communicating with Shure receiver: {err}") from err
