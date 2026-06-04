from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.dt import utcnow

from .const import (
    CONF_GRACE_PERIOD,
    CONF_POLL_INTERVAL,
    CONF_TRACKED_DEVICES,
    DEFAULT_GRACE_PERIOD,
    DEFAULT_POLL_INTERVAL,
    DEVICE_MANUFACTURER_KEY,
    DEVICE_MODEL_KEY,
    DEVICE_NAME_KEY,
    DOMAIN,
)
from .models import CoordinatorData, RouterInfo, TrackedDevice
from .routeros_client import (
    MikrotikAuthError,
    MikrotikConnectionError,
    MikrotikRouterOSClient,
    MikrotikUnsupportedError,
)

LOGGER = logging.getLogger(__name__)


class MikrotikWiFiRegistrationCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinate RouterOS registration-table polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry,
        client: MikrotikRouterOSClient,
    ) -> None:
        self.config_entry = entry
        self.client = client
        self.router_info: RouterInfo | None = None
        self.dhcp_hostnames: dict[str, str] = {}
        self._last_seen: dict[str, datetime] = {}
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )

    @property
    def grace_period(self) -> timedelta:
        return timedelta(
            seconds=self.config_entry.options.get(
                CONF_GRACE_PERIOD, DEFAULT_GRACE_PERIOD
            )
        )

    @property
    def tracked_devices(self) -> dict[str, TrackedDevice]:
        tracked: dict[str, TrackedDevice] = {}
        raw_devices = self.config_entry.options.get(CONF_TRACKED_DEVICES, {})
        for mac_address, payload in raw_devices.items():
            normalized_mac = format_mac(mac_address)
            tracked[normalized_mac] = TrackedDevice(
                mac_address=normalized_mac,
                name=payload.get(DEVICE_NAME_KEY, normalized_mac),
                manufacturer=payload.get(DEVICE_MANUFACTURER_KEY),
                model=payload.get(DEVICE_MODEL_KEY),
            )
        return tracked

    @property
    def tracked_macs(self) -> list[str]:
        return list(self.tracked_devices)

    async def _async_setup(self) -> None:
        discovery = await self.client.async_discover()
        self.router_info = discovery.router_info
        self.dhcp_hostnames = discovery.dhcp_hostnames

    async def _async_update_data(self) -> CoordinatorData:
        try:
            registrations = await self.client.async_fetch_registration_table()
        except MikrotikAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MikrotikUnsupportedError as err:
            raise UpdateFailed(str(err)) from err
        except MikrotikConnectionError as err:
            raise UpdateFailed(str(err)) from err

        fetched_at = utcnow()
        for mac_address in registrations:
            self._last_seen[mac_address] = fetched_at

        return CoordinatorData(registrations=registrations, fetched_at=fetched_at)

    def last_seen(self, mac_address: str):
        return self._last_seen.get(format_mac(mac_address))

    def off_transition_at(self, mac_address: str):
        last_seen = self.last_seen(mac_address)
        if last_seen is None:
            return None
        return last_seen + self.grace_period
