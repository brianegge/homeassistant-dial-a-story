"""TCP client for Shure SLX-D receivers.

Shure wireless receivers expose a command-string interface on TCP port 2202.
Commands use the format: < GET channel PARAMETER >
Responses use the format: < REP channel PARAMETER {value} >
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .const import CONNECTION_TIMEOUT, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)

# Regex to parse Shure response lines: < REP channel PARAMETER {value} >
_REP_PATTERN = re.compile(r"<\s*REP\s+(\d+)\s+(\w+)\s+\{?(.*?)\}?\s*>")
_SAMPLE_PATTERN = re.compile(r"<\s*SAMPLE\s+(\d+)\s+ALL\s+(.*?)\s*>")


@dataclass
class ChannelData:
    """Data for a single receiver channel."""

    chan_name: str = ""
    battery_bars: int | None = None
    battery_charge: int | None = None
    battery_run_time: int | None = None
    battery_type: str = ""
    tx_type: str = ""
    frequency: str = ""
    group_chan: str = ""
    antenna: str = ""
    rf_int_det: str = ""
    audio_level: int | None = None
    rf_level_a: int | None = None
    rf_level_b: int | None = None


@dataclass
class DeviceInfo:
    """Device-level information."""

    model: str = ""
    fw_ver: str = ""
    device_id: str = ""


@dataclass
class ReceiverData:
    """All data from a Shure SLX-D receiver."""

    device: DeviceInfo = field(default_factory=DeviceInfo)
    channels: dict[int, ChannelData] = field(default_factory=dict)


class ShureClient:
    """Async TCP client for Shure SLX-D receivers."""

    def __init__(self, host: str, port: int = DEFAULT_PORT) -> None:
        self._host = host
        self._port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    @property
    def host(self) -> str:
        """Return the host address."""
        return self._host

    async def connect(self) -> None:
        """Open TCP connection to the receiver."""
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port),
            timeout=CONNECTION_TIMEOUT,
        )
        _LOGGER.debug("Connected to Shure receiver at %s:%d", self._host, self._port)

    async def disconnect(self) -> None:
        """Close the TCP connection."""
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def _send_command(self, command: str) -> None:
        """Send a command string to the receiver."""
        if not self._writer:
            raise ConnectionError("Not connected to receiver")
        full_command = f"< {command} >\r\n"
        self._writer.write(full_command.encode("ascii"))
        await self._writer.drain()
        _LOGGER.debug("Sent: %s", full_command.strip())

    async def _read_responses(self, timeout: float = 2.0) -> list[str]:
        """Read available response lines from the receiver."""
        if not self._reader:
            raise ConnectionError("Not connected to receiver")
        lines: list[str] = []
        try:
            while True:
                line_bytes = await asyncio.wait_for(
                    self._reader.readline(),
                    timeout=timeout,
                )
                if not line_bytes:
                    break
                line = line_bytes.decode("ascii", errors="replace").strip()
                if line:
                    lines.append(line)
                    _LOGGER.debug("Recv: %s", line)
        except TimeoutError:
            pass
        return lines

    def _parse_response(self, line: str, data: ReceiverData) -> None:
        """Parse a single response line into ReceiverData."""
        match = _REP_PATTERN.match(line)
        if match:
            channel = int(match.group(1))
            param = match.group(2)
            value = match.group(3).strip()
            self._apply_param(data, channel, param, value)
            return

        sample_match = _SAMPLE_PATTERN.match(line)
        if sample_match:
            channel = int(sample_match.group(1))
            values = sample_match.group(2).split()
            if channel not in data.channels:
                data.channels[channel] = ChannelData()
            ch = data.channels[channel]
            # SAMPLE format: RF_LVL_A RF_LVL_B AUDIO_LVL (3-digit values)
            if len(values) >= 3:
                ch.rf_level_a = _parse_int(values[0])
                ch.rf_level_b = _parse_int(values[1])
                ch.audio_level = _parse_int(values[2])

    def _apply_param(self, data: ReceiverData, channel: int, param: str, value: str) -> None:
        """Apply a parsed parameter to the appropriate data structure."""
        if channel == 0:
            self._apply_device_param(data.device, param, value)
        else:
            if channel not in data.channels:
                data.channels[channel] = ChannelData()
            self._apply_channel_param(data.channels[channel], param, value)

    def _apply_device_param(self, device: DeviceInfo, param: str, value: str) -> None:
        """Apply a device-level parameter."""
        if param == "MODEL":
            device.model = value
        elif param == "FW_VER":
            device.fw_ver = value
        elif param == "DEVICE_ID":
            device.device_id = value

    def _apply_channel_param(self, ch: ChannelData, param: str, value: str) -> None:
        """Apply a channel-level parameter."""
        if param == "CHAN_NAME":
            ch.chan_name = value
        elif param == "BATTERY_BARS":
            ch.battery_bars = _parse_int(value)
        elif param == "BATTERY_CHARGE":
            ch.battery_charge = _parse_int(value)
        elif param == "BATTERY_RUN_TIME":
            parsed = _parse_int(value)
            ch.battery_run_time = parsed if parsed != 65535 else None
        elif param == "BATTERY_TYPE":
            ch.battery_type = value
        elif param == "TX_TYPE":
            ch.tx_type = value
        elif param == "FREQUENCY":
            ch.frequency = value
        elif param == "GROUP_CHAN":
            ch.group_chan = value
        elif param == "ANTENNA":
            ch.antenna = value
        elif param == "RF_INT_DET":
            ch.rf_int_det = value
        elif param == "AUDIO_LVL":
            ch.audio_level = _parse_int(value)

    async def get_device_info(self) -> dict[str, str]:
        """Query device-level information."""
        data = ReceiverData()
        for param in ("MODEL", "FW_VER", "DEVICE_ID"):
            await self._send_command(f"GET 0 {param}")

        for line in await self._read_responses():
            self._parse_response(line, data)

        return {
            "model": data.device.model,
            "fw_ver": data.device.fw_ver,
            "device_id": data.device.device_id,
        }

    async def poll_all(self, num_channels: int) -> ReceiverData:
        """Poll all data from the receiver."""
        data = ReceiverData()

        # Query device info
        for param in ("MODEL", "FW_VER", "DEVICE_ID"):
            await self._send_command(f"GET 0 {param}")

        # Query each channel
        channel_params = (
            "CHAN_NAME",
            "BATTERY_BARS",
            "BATTERY_CHARGE",
            "BATTERY_RUN_TIME",
            "BATTERY_TYPE",
            "TX_TYPE",
            "FREQUENCY",
            "GROUP_CHAN",
            "ANTENNA",
            "RF_INT_DET",
        )
        for ch in range(1, num_channels + 1):
            for param in channel_params:
                await self._send_command(f"GET {ch} {param}")

        for line in await self._read_responses():
            self._parse_response(line, data)

        return data

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return device info."""
        await self.connect()
        try:
            return await self.get_device_info()
        finally:
            await self.disconnect()


def _parse_int(value: str) -> int | None:
    """Parse an integer value, returning None for unknown/invalid values."""
    try:
        parsed = int(value)
        # 255 and 65535 are common "unknown" sentinel values
        if parsed in (255, 65535):
            return None
        return parsed
    except (ValueError, TypeError):
        return None
