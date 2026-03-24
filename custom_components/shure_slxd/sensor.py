"""Sensor entities for Shure SLX-D receivers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import ChannelData
from .const import DOMAIN
from .coordinator import ShureCoordinator


@dataclass(frozen=True, kw_only=True)
class ShureChannelSensorDescription(SensorEntityDescription):
    """Description for a Shure channel sensor."""

    value_fn: Callable[[ChannelData], Any]


CHANNEL_SENSORS: tuple[ShureChannelSensorDescription, ...] = (
    ShureChannelSensorDescription(
        key="batt_bars",
        translation_key="batt_bars",
        native_unit_of_measurement="bars",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        value_fn=lambda ch: ch.batt_bars,
    ),
    ShureChannelSensorDescription(
        key="batt_charge",
        translation_key="batt_charge",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.batt_charge,
    ),
    ShureChannelSensorDescription(
        key="batt_run_time",
        translation_key="batt_run_time",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda ch: ch.batt_run_time,
    ),
    ShureChannelSensorDescription(
        key="batt_type",
        translation_key="batt_type",
        icon="mdi:battery-unknown",
        value_fn=lambda ch: ch.batt_type or None,
    ),
    ShureChannelSensorDescription(
        key="rf_level",
        translation_key="rf_level",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
        value_fn=lambda ch: ch.rf_level,
    ),
    ShureChannelSensorDescription(
        key="audio_level_peak",
        translation_key="audio_level_peak",
        native_unit_of_measurement="dBFS",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:volume-high",
        value_fn=lambda ch: ch.audio_level_peak,
    ),
    ShureChannelSensorDescription(
        key="audio_gain",
        translation_key="audio_gain",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:knob",
        value_fn=lambda ch: ch.audio_gain,
    ),
    ShureChannelSensorDescription(
        key="frequency",
        translation_key="frequency",
        icon="mdi:sine-wave",
        value_fn=lambda ch: _format_frequency(ch.frequency) if ch.frequency else None,
    ),
    ShureChannelSensorDescription(
        key="tx_model",
        translation_key="tx_model",
        icon="mdi:microphone",
        value_fn=lambda ch: ch.tx_model if ch.tx_model and ch.tx_model != "UNKNOWN" else None,
    ),
    ShureChannelSensorDescription(
        key="rf_interference",
        translation_key="rf_interference",
        icon="mdi:alert-circle-outline",
        value_fn=lambda ch: ch.rf_int_det or None,
    ),
    ShureChannelSensorDescription(
        key="audio_mute",
        translation_key="audio_mute",
        icon="mdi:volume-off",
        value_fn=lambda ch: ch.audio_mute or None,
    ),
    ShureChannelSensorDescription(
        key="chan_name",
        translation_key="chan_name",
        icon="mdi:label-outline",
        value_fn=lambda ch: ch.chan_name.strip() if ch.chan_name else None,
    ),
)


def _format_frequency(freq_str: str) -> str | None:
    """Format a 6-digit frequency string as MHz (e.g., 470125 -> 470.125 MHz)."""
    if len(freq_str) == 6 and freq_str.isdigit():
        mhz = int(freq_str[:3])
        khz = int(freq_str[3:])
        return f"{mhz}.{khz:03d}"
    return freq_str


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Shure SLX-D sensors from a config entry."""
    coordinator: ShureCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[ShureChannelSensor] = []
    for ch_num in range(1, coordinator.num_channels + 1):
        for description in CHANNEL_SENSORS:
            entities.append(ShureChannelSensor(coordinator, entry, ch_num, description))

    async_add_entities(entities)


class ShureChannelSensor(CoordinatorEntity[ShureCoordinator], SensorEntity):
    """Sensor for a single metric on a Shure receiver channel."""

    entity_description: ShureChannelSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ShureCoordinator,
        entry: ConfigEntry,
        channel: int,
        description: ShureChannelSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._channel = channel
        self._attr_unique_id = f"{entry.entry_id}_ch{channel}_{description.key}"
        self._attr_translation_placeholders = {"channel": str(channel)}

        device_data = coordinator.data
        model = device_data.device.model if device_data else "SLXD4"
        device_id = device_data.device.device_id if device_data else entry.entry_id

        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": f"Shure {model} Ch {channel}",
            "manufacturer": "Shure",
            "model": model,
            "sw_version": device_data.device.fw_ver if device_data else None,
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if not self.coordinator.data:
            return None
        channel_data = self.coordinator.data.channels.get(self._channel)
        if not channel_data:
            return None
        return self.entity_description.value_fn(channel_data)

    @property
    def available(self) -> bool:
        """Return True if the sensor is available."""
        return super().available and self.coordinator.data is not None
