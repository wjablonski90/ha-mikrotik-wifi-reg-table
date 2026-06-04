from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import MikrotikWiFiRegistrationCoordinator


class MikrotikWiFiRegistrationEntity(
    CoordinatorEntity[MikrotikWiFiRegistrationCoordinator]
):
    """Base entity for tracked MikroTik WiFi clients."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MikrotikWiFiRegistrationCoordinator,
        mac_address: str,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        tracked_device = coordinator.tracked_devices[mac_address]
        self._mac_address = mac_address
        self._attr_unique_id = f"{mac_address}|{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac_address)},
            name=tracked_device.name,
            manufacturer=tracked_device.manufacturer,
            model=tracked_device.model,
        )

    @property
    def tracked_name(self) -> str:
        return self.coordinator.tracked_devices[self._mac_address].name

    def build_suggested_object_id(self, suffix: str) -> str:
        return f"{slugify(self.tracked_name)}_{slugify(suffix)}"

    @property
    def registration(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.registrations.get(self._mac_address)
