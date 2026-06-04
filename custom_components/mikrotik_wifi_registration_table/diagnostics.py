from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD
from homeassistant.helpers.device_registry import DeviceEntry

from . import MikrotikWifiRegistrationConfigEntry
from .const import CONF_POLL_INTERVAL, CONF_TRACKED_DEVICES, DOMAIN

TO_REDACT = {CONF_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass, entry: MikrotikWifiRegistrationConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data.coordinator
    tracked = coordinator.tracked_devices
    connected = 0
    if coordinator.data is not None:
        connected = sum(
            1 for mac_address in tracked if mac_address in coordinator.data.registrations
        )

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "router": {
            "identity": coordinator.router_info.identity if coordinator.router_info else None,
            "version": coordinator.router_info.version if coordinator.router_info else None,
            "board_name": coordinator.router_info.board_name
            if coordinator.router_info
            else None,
            "serial_number": coordinator.router_info.serial_number
            if coordinator.router_info
            else None,
        },
        "poll_interval": entry.options.get(CONF_POLL_INTERVAL),
        "tracked_devices_count": len(tracked),
        "currently_connected_devices": connected,
        "visible_registration_rows": len(coordinator.data.registrations)
        if coordinator.data is not None
        else 0,
        "tracked_devices": entry.options.get(CONF_TRACKED_DEVICES, {}),
    }


async def async_get_device_diagnostics(
    hass,
    entry: MikrotikWifiRegistrationConfigEntry,
    device: DeviceEntry,
) -> dict[str, Any]:
    """Return diagnostics for a tracked device."""
    coordinator = entry.runtime_data.coordinator
    mac_address = next(
        (
            identifier[1]
            for identifier in device.identifiers
            if identifier[0] == DOMAIN
        ),
        None,
    )
    registration = (
        coordinator.data.registrations.get(mac_address)
        if mac_address and coordinator.data is not None
        else None
    )

    return {
        "device": {
            "name": device.name,
            "manufacturer": device.manufacturer,
            "model": device.model,
            "identifiers": list(device.identifiers),
        },
        "tracked_device": _tracked_device_payload(
            coordinator.tracked_devices.get(mac_address)
        ),
        "current_registration": {
            "connected": registration is not None,
            "ip_address": registration.ip_address if registration else None,
            "ssid": registration.ssid if registration else None,
            "interface": registration.interface if registration else None,
            "signal_dbm": registration.signal_dbm if registration else None,
            "tx_rate_mbps": registration.tx_rate_mbps if registration else None,
            "rx_rate_mbps": registration.rx_rate_mbps if registration else None,
            "uptime_seconds": int(registration.uptime.total_seconds())
            if registration and registration.uptime is not None
            else None,
            "last_activity_seconds": int(registration.last_activity.total_seconds())
            if registration and registration.last_activity is not None
            else None,
            "band": registration.band if registration else None,
            "auth_type": registration.auth_type if registration else None,
            "raw": registration.raw if registration else None,
        },
        "last_seen": coordinator.last_seen(mac_address).isoformat()
        if mac_address and coordinator.last_seen(mac_address) is not None
        else None,
    }


def _tracked_device_payload(tracked_device) -> dict[str, Any] | None:
    if tracked_device is None:
        return None
    return {
        "mac_address": tracked_device.mac_address,
        "name": tracked_device.name,
        "manufacturer": tracked_device.manufacturer,
        "model": tracked_device.model,
    }
