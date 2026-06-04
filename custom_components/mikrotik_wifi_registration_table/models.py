from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass(slots=True)
class RouterInfo:
    unique_id: str
    identity: str
    version: str | None
    board_name: str | None
    serial_number: str | None
    software_id: str | None


@dataclass(slots=True)
class RegistrationEntry:
    mac_address: str
    hostname: str | None
    ip_address: str | None
    ssid: str | None
    interface: str | None
    signal_dbm: int | None
    tx_rate_mbps: float | None
    rx_rate_mbps: float | None
    uptime: timedelta | None
    last_activity: timedelta | None
    band: str | None
    auth_type: str | None
    raw: dict[str, str]


@dataclass(slots=True)
class CoordinatorData:
    registrations: dict[str, RegistrationEntry]
    fetched_at: datetime


@dataclass(slots=True)
class TrackedDevice:
    mac_address: str
    name: str
    manufacturer: str | None = None
    model: str | None = None


@dataclass(slots=True)
class RouterDiscoveryData:
    router_info: RouterInfo
    registrations: dict[str, RegistrationEntry]
    dhcp_hostnames: dict[str, str]


@dataclass(slots=True)
class TrackedDevicePayload:
    name: str
    manufacturer: str | None
    model: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "model": self.model,
        }
