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
        key="battery_bars",
        translation_key="battery_bars",
        native_unit_of_measurement="bars",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:battery",
        value_fn=lambda ch: ch.battery_bars,
    ),
    ShureChannelSensorDescription(
        key="battery_charge",
        translation_key="battery_charge",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ch: ch.battery_charge,
    ),
    ShureChannelSensorDescription(
        key="battery_run_time",
        translation_key="battery_run_time",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:timer-outline",
        value_fn=lambda ch: ch.battery_run_time,
    ),
    ShureChannelSensorDescription(
        key="battery_type",
        translation_key="battery_type",
        icon="mdi:battery-unknown",
        value_fn=lambda ch: ch.battery_type or None,
    ),
    ShureChannelSensorDescription(
        key="rf_level_a",
        translation_key="rf_level_a",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
        value_fn=lambda ch: ch.rf_level_a,
    ),
    ShureChannelSensorDescription(
        key="rf_level_b",
        translation_key="rf_level_b",
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:signal",
        value_fn=lambda ch: ch.rf_level_b,
    ),
    ShureChannelSensorDescription(
        key="audio_level",
        translation_key="audio_level",
        native_unit_of_measurement="dB",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:volume-high",
        value_fn=lambda ch: ch.audio_level,
    ),
    ShureChannelSensorDescription(
        key="antenna",
        translation_key="antenna",
        icon="mdi:antenna",
        value_fn=lambda ch: ch.antenna or None,
    ),
    ShureChannelSensorDescription(
        key="frequency",
        translation_key="frequency",
        icon="mdi:sine-wave",
        value_fn=lambda ch: ch.frequency or None,
    ),
    ShureChannelSensorDescription(
        key="tx_type",
        translation_key="tx_type",
        icon="mdi:microphone",
        value_fn=lambda ch: ch.tx_type or None,
    ),
    ShureChannelSensorDescription(
        key="rf_interference",
        translation_key="rf_interference",
        icon="mdi:alert-circle-outline",
        value_fn=lambda ch: ch.rf_int_det or None,
    ),
    ShureChannelSensorDescription(
        key="chan_name",
        translation_key="chan_name",
        icon="mdi:label-outline",
        value_fn=lambda ch: ch.chan_name or None,
    ),
)


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
