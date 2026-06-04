from __future__ import annotations

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.const import STATE_HOME, STATE_NOT_HOME
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util.dt import utcnow

from . import MikrotikWifiRegistrationConfigEntry
from .const import PRESENCE_TRACKER_SUFFIX
from .coordinator import MikrotikWiFiRegistrationCoordinator
from .entity import MikrotikWiFiRegistrationEntity


async def async_setup_entry(
    hass,
    entry: MikrotikWifiRegistrationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        [
            MikrotikWiFiClientTracker(coordinator, mac_address)
            for mac_address in coordinator.tracked_macs
        ]
    )


class MikrotikWiFiClientTracker(MikrotikWiFiRegistrationEntity, TrackerEntity):
    """Device tracker backed by the WiFi registration table."""

    _attr_name = "Presence"
    _attr_source_type = SourceType.ROUTER

    def __init__(
        self, coordinator: MikrotikWiFiRegistrationCoordinator, mac_address: str
    ) -> None:
        super().__init__(coordinator, mac_address, PRESENCE_TRACKER_SUFFIX)
        self._grace_unsub = None
        self._attr_suggested_object_id = self.build_suggested_object_id(
            PRESENCE_TRACKER_SUFFIX
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._schedule_grace_expiry()

    async def async_will_remove_from_hass(self) -> None:
        if self._grace_unsub is not None:
            self._grace_unsub()
            self._grace_unsub = None
        await super().async_will_remove_from_hass()

    @property
    def _presence_is_home(self) -> bool:
        if self.registration is not None:
            return True

        last_seen = self.coordinator.last_seen(self._mac_address)
        if last_seen is None:
            return False

        return utcnow() <= last_seen + self.coordinator.grace_period

    @property
    def location_name(self) -> str:
        return STATE_HOME if self._presence_is_home else STATE_NOT_HOME

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        last_seen = self.coordinator.last_seen(self._mac_address)
        registration = self.registration
        tracked = self.coordinator.tracked_devices[self._mac_address]
        return {
            "mac_address": self._mac_address,
            "last_seen": last_seen.isoformat() if last_seen is not None else None,
            "hostname": registration.hostname if registration is not None else tracked.name,
            "ip_address": registration.ip_address if registration is not None else None,
            "ssid": registration.ssid if registration is not None else None,
            "interface": registration.interface if registration is not None else None,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        self._schedule_grace_expiry()
        super()._handle_coordinator_update()

    @callback
    def _schedule_grace_expiry(self) -> None:
        if self._grace_unsub is not None:
            self._grace_unsub()
            self._grace_unsub = None

        if self.registration is not None:
            return

        expiry = self.coordinator.off_transition_at(self._mac_address)
        if expiry is None or expiry <= utcnow():
            return

        self._grace_unsub = async_track_point_in_utc_time(
            self.hass, self._async_grace_expired, expiry
        )

    @callback
    def _async_grace_expired(self, _now) -> None:
        self._grace_unsub = None
        self.async_write_ha_state()
