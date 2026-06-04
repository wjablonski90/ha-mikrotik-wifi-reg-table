from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import (
    PRESENCE_TRACKER_SUFFIX,
    CONF_TRACKED_DEVICES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MikrotikWiFiRegistrationCoordinator
from .routeros_client import MikrotikRouterOSClient


@dataclass(slots=True)
class MikrotikWifiRegistrationRuntimeData:
    client: MikrotikRouterOSClient
    coordinator: MikrotikWiFiRegistrationCoordinator


MikrotikWifiRegistrationConfigEntry = ConfigEntry[MikrotikWifiRegistrationRuntimeData]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration."""
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MikrotikWifiRegistrationConfigEntry,
) -> bool:
    """Set up MikroTik WiFi Registration Table from a config entry."""
    client = MikrotikRouterOSClient(
        hass,
        host=entry.data["host"],
        username=entry.data["username"],
        password=entry.data["password"],
        port=entry.data["port"],
    )
    coordinator = MikrotikWiFiRegistrationCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = MikrotikWifiRegistrationRuntimeData(
        client=client,
        coordinator=coordinator,
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await _async_prune_stale_entities(hass, entry)
    await _async_migrate_entity_ids(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: MikrotikWifiRegistrationConfigEntry,
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_close()
    return unload_ok


async def async_reload_entry(
    hass: HomeAssistant,
    entry: MikrotikWifiRegistrationConfigEntry,
) -> None:
    """Reload a config entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: MikrotikWifiRegistrationConfigEntry,
    device_id: str,
) -> bool:
    """Allow removing client devices from Home Assistant."""
    return True


async def _async_prune_stale_entities(
    hass: HomeAssistant, entry: MikrotikWifiRegistrationConfigEntry
) -> None:
    entity_registry = er.async_get(hass)
    tracked_macs = set(entry.options.get(CONF_TRACKED_DEVICES, {}))
    valid_tracker_ids = tracked_macs | {
        f"{mac_address}|{PRESENCE_TRACKER_SUFFIX}" for mac_address in tracked_macs
    }
    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity_entry.platform == "binary_sensor":
            entity_registry.async_remove(entity_entry.entity_id)
            continue
        if (
            entity_entry.platform == "device_tracker"
            and entity_entry.unique_id not in valid_tracker_ids
        ):
            entity_registry.async_remove(entity_entry.entity_id)
            continue
        if entity_entry.unique_id is None:
            continue
        entity_mac, _, _ = entity_entry.unique_id.partition("|")
        if entity_mac and entity_mac not in tracked_macs:
            entity_registry.async_remove(entity_entry.entity_id)


async def _async_migrate_entity_ids(
    hass: HomeAssistant, entry: MikrotikWifiRegistrationConfigEntry
) -> None:
    """Rename fallback entity_ids to friendly tracked-device names.

    Also drop orphaned device_tracker registry rows so Home Assistant can
    recreate them with the correct device association.
    """
    entity_registry = er.async_get(hass)
    tracked_devices = entry.runtime_data.coordinator.tracked_devices

    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity_entry.unique_id is None:
            continue

        entity_mac, _, suffix = entity_entry.unique_id.partition("|")
        if entity_entry.platform == "device_tracker" and entity_entry.unique_id in tracked_devices:
            entity_mac = entity_entry.unique_id
            suffix = PRESENCE_TRACKER_SUFFIX

        if not entity_mac or not suffix:
            continue

        tracked_device = tracked_devices.get(entity_mac)
        if tracked_device is None:
            continue

        if entity_entry.platform == "device_tracker" and entity_entry.device_id is None:
            entity_registry.async_remove(entity_entry.entity_id)
            continue

        object_id = (
            f"{slugify(tracked_device.name)}_{slugify(suffix)}"
            if entity_entry.platform in {"device_tracker", "sensor"}
            else None
        )
        if object_id is None:
            continue

        desired_entity_id = f"{entity_entry.platform}.{object_id}"
        if entity_entry.entity_id == desired_entity_id:
            continue

        if not entity_entry.entity_id.startswith(
            f"{entity_entry.platform}.{DOMAIN}_"
        ):
            continue

        if entity_registry.async_get(desired_entity_id) is not None:
            continue

        entity_registry.async_update_entity(
            entity_entry.entity_id,
            new_entity_id=desired_entity_id,
        )
