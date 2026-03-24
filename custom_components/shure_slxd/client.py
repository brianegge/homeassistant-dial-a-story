"""TCP client for Shure SLX-D receivers.

Shure wireless receivers expose a command-string interface on TCP port 2202.
Commands use the format: < GET channel PARAMETER >
Responses use the format: < REP channel PARAMETER {value} >
Metering uses: < SAMPLE channel values... >

Reference: https://pubs.shure.com/command-strings/SLXD/en-US
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

# Regex to parse Shure response lines
# Device-level: < REP PARAMETER {value} >
_REP_DEVICE_PATTERN = re.compile(r"<\s*REP\s+([A-Z_]+)\s+\{?(.*?)\}?\s*>")
# Channel-level: < REP channel PARAMETER {value} >
_REP_CHANNEL_PATTERN = re.compile(r"<\s*REP\s+(\d+)\s+(\w+)\s+\{?(.*?)\}?\s*>")
# Metering: < SAMPLE channel ALL peak rms rf_level >
_SAMPLE_PATTERN = re.compile(r"<\s*SAMPLE\s+(\d+)\s+ALL\s+(.*?)\s*>")

# Sentinel values meaning "unknown" in the Shure protocol
_UNKNOWN_BYTE = 255
_UNKNOWN_WORD = 65535
_CALCULATING = 65534


@dataclass
class ChannelData:
    """Data for a single receiver channel."""

    chan_name: str = ""
    batt_bars: int | None = None
    batt_charge: int | None = None
    batt_run_time: int | None = None
    batt_type: str = ""
    tx_model: str = ""
    tx_type: str = ""
    frequency: str = ""
    group_channel: str = ""
    audio_gain: int | None = None
    audio_mute: str = ""
    rf_int_det: str = ""
    audio_level_peak: int | None = None
    audio_level_rms: int | None = None
    rf_level: int | None = None


@dataclass
class DeviceInfo:
    """Device-level information."""

    model: str = ""
    fw_ver: str = ""
    device_id: str = ""
    rf_band: str = ""
    encryption: str = ""


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
        # Try channel-level REP first (has a digit after REP)
        match = _REP_CHANNEL_PATTERN.match(line)
        if match:
            channel = int(match.group(1))
            param = match.group(2)
            value = match.group(3).strip()
            if channel == 0:
                self._apply_device_param(data.device, param, value)
            else:
                if channel not in data.channels:
                    data.channels[channel] = ChannelData()
                self._apply_channel_param(data.channels[channel], param, value)
            return

        # Try device-level REP (no channel number)
        dev_match = _REP_DEVICE_PATTERN.match(line)
        if dev_match:
            param = dev_match.group(1)
            value = dev_match.group(2).strip()
            self._apply_device_param(data.device, param, value)
            return

        # Try SAMPLE metering line
        sample_match = _SAMPLE_PATTERN.match(line)
        if sample_match:
            channel = int(sample_match.group(1))
            values = sample_match.group(2).split()
            if channel not in data.channels:
                data.channels[channel] = ChannelData()
            ch = data.channels[channel]
            # SAMPLE format after ALL: AUDIO_LVL_PEAK AUDIO_LVL_RMS RF_LVL
            # Raw values are 0-120; actual dBFS/dBm = raw - 120
            if len(values) >= 3:
                ch.audio_level_peak = _sample_to_db(values[0])
                ch.audio_level_rms = _sample_to_db(values[1])
                ch.rf_level = _sample_to_db(values[2])

    def _apply_device_param(self, device: DeviceInfo, param: str, value: str) -> None:
        """Apply a device-level parameter."""
        if param == "MODEL":
            device.model = value
        elif param == "FW_VER":
            device.fw_ver = value
        elif param == "DEVICE_ID":
            device.device_id = value
        elif param == "RF_BAND":
            device.rf_band = value
        elif param == "ENCRYPTION":
            device.encryption = value

    def _apply_channel_param(self, ch: ChannelData, param: str, value: str) -> None:
        """Apply a channel-level parameter."""
        if param == "CHAN_NAME":
            ch.chan_name = value
        elif param in ("BATT_BARS", "TX_BATT_BARS"):
            ch.batt_bars = _parse_int(value)
        elif param == "BATT_CHARGE":
            ch.batt_charge = _parse_int(value)
        elif param in ("BATT_RUN_TIME", "TX_BATT_MINS"):
            parsed = _parse_int(value)
            # 65534 means "calculating", treat as unknown
            ch.batt_run_time = parsed if parsed not in (_UNKNOWN_WORD, _CALCULATING, None) else None
        elif param == "BATT_TYPE":
            ch.batt_type = value
        elif param == "TX_MODEL":
            ch.tx_model = value
        elif param == "TX_TYPE":
            ch.tx_type = value
        elif param == "FREQUENCY":
            ch.frequency = value
        elif param == "GROUP_CHANNEL":
            ch.group_channel = value
        elif param == "AUDIO_GAIN":
            ch.audio_gain = _parse_int(value)
        elif param == "AUDIO_MUTE":
            ch.audio_mute = value
        elif param == "RF_INT_DET":
            ch.rf_int_det = value

    async def get_device_info(self) -> dict[str, str]:
        """Query device-level information."""
        data = ReceiverData()
        for param in ("MODEL", "FW_VER", "DEVICE_ID"):
            await self._send_command(f"GET {param}")

        for line in await self._read_responses():
            self._parse_response(line, data)

        return {
            "model": data.device.model,
            "fw_ver": data.device.fw_ver,
            "device_id": data.device.device_id,
        }

    async def poll_all(self, num_channels: int) -> ReceiverData:
        """Poll all data from the receiver using GET 0 ALL."""
        data = ReceiverData()

        # GET 0 ALL retrieves all parameters for all channels at once
        await self._send_command("GET 0 ALL")

        for line in await self._read_responses(timeout=3.0):
            self._parse_response(line, data)

        return data

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return device info."""
        await self.connect()
        try:
            return await self.get_device_info()
        finally:
            await self.disconnect()


def _sample_to_db(value: str) -> int | None:
    """Convert a SAMPLE raw value (0-120) to dB (actual = raw - 120)."""
    try:
        raw = int(value)
        return raw - 120
    except (ValueError, TypeError):
        return None


def _parse_int(value: str) -> int | None:
    """Parse an integer value, returning None for unknown/invalid values."""
    try:
        parsed = int(value)
        # 255 is "unknown" for byte-sized values (battery bars, etc.)
        if parsed == _UNKNOWN_BYTE:
            return None
        return parsed
    except (ValueError, TypeError):
        return None
