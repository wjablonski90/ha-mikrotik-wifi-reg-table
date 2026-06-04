from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfDataRate,
    UnitOfTime,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MikrotikWifiRegistrationConfigEntry
from .entity import MikrotikWiFiRegistrationEntity
from .models import RegistrationEntry


@dataclass(frozen=True, kw_only=True)
class MikrotikWiFiSensorDescription(SensorEntityDescription):
    value_fn: Callable[[RegistrationEntry], str | int | float | None]


SENSOR_DESCRIPTIONS: tuple[MikrotikWiFiSensorDescription, ...] = (
    MikrotikWiFiSensorDescription(
        key="signal",
        name="Signal",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entry: entry.signal_dbm,
    ),
    MikrotikWiFiSensorDescription(
        key="tx_rate",
        name="TX rate",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda entry: entry.tx_rate_mbps,
    ),
    MikrotikWiFiSensorDescription(
        key="rx_rate",
        name="RX rate",
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda entry: entry.rx_rate_mbps,
    ),
    MikrotikWiFiSensorDescription(
        key="uptime",
        name="Uptime",
        value_fn=lambda entry: _format_duration(entry.uptime),
    ),
    MikrotikWiFiSensorDescription(
        key="last_activity",
        name="Last activity",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entry: int(entry.last_activity.total_seconds())
        if entry.last_activity is not None
        else None,
    ),
    MikrotikWiFiSensorDescription(
        key="ssid",
        name="SSID",
        value_fn=lambda entry: entry.ssid,
    ),
    MikrotikWiFiSensorDescription(
        key="band",
        name="Band",
        value_fn=lambda entry: entry.band,
    ),
    MikrotikWiFiSensorDescription(
        key="auth_type",
        name="Auth type",
        value_fn=lambda entry: entry.auth_type,
    ),
)


async def async_setup_entry(
    hass,
    entry: MikrotikWifiRegistrationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    entities: list[MikrotikWiFiClientSensor] = []
    for mac_address in coordinator.tracked_macs:
        entities.extend(
            MikrotikWiFiClientSensor(coordinator, mac_address, description)
            for description in SENSOR_DESCRIPTIONS
        )
    async_add_entities(entities)


class MikrotikWiFiClientSensor(MikrotikWiFiRegistrationEntity, SensorEntity):
    """Sensors for a tracked WiFi client."""

    entity_description: MikrotikWiFiSensorDescription

    def __init__(self, coordinator, mac_address, description) -> None:
        super().__init__(coordinator, mac_address, description.key)
        self.entity_description = description
        self._attr_suggested_object_id = self.build_suggested_object_id(
            description.key
        )

    @property
    def native_value(self):
        registration = self.registration
        if registration is None:
            return None
        return self.entity_description.value_fn(registration)


def _format_duration(duration) -> str | None:
    if duration is None:
        return None

    total_seconds = int(duration.total_seconds())
    if total_seconds <= 0:
        return "0s"

    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not parts:
        parts.append(f"{seconds}s")
    elif seconds and len(parts) < 2:
        parts.append(f"{seconds}s")

    return " ".join(parts[:3])
