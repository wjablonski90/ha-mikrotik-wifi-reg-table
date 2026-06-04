from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import format_mac
import routeros

from .const import (
    DEFAULT_TIMEOUT,
    DHCP_LEASES_PATH,
    REGISTRATION_TABLE_PATH,
    SUPPORTED_ROUTEROS_MAJOR,
    SYSTEM_IDENTITY_PATH,
    SYSTEM_LICENSE_PATH,
    SYSTEM_RESOURCE_PATH,
    SYSTEM_ROUTERBOARD_PATH,
)
from .models import RegistrationEntry, RouterDiscoveryData, RouterInfo

LOGGER = logging.getLogger(__name__)

_RATE_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*([kmg]?)(?:bit/s|bps|mbps)?", re.IGNORECASE)
_DBM_RE = re.compile(r"(-?\d+)")

_MODEL_PATTERNS: tuple[tuple[re.Pattern[str], tuple[str, str]], ...] = (
    (re.compile(r"iphone", re.IGNORECASE), ("Apple", "iPhone")),
    (re.compile(r"ipad", re.IGNORECASE), ("Apple", "iPad")),
    (re.compile(r"macbook", re.IGNORECASE), ("Apple", "MacBook")),
    (re.compile(r"\bimac\b", re.IGNORECASE), ("Apple", "iMac")),
    (re.compile(r"apple[\s_-]?watch", re.IGNORECASE), ("Apple", "Apple Watch")),
    (re.compile(r"airpods", re.IGNORECASE), ("Apple", "AirPods")),
    (re.compile(r"galaxy", re.IGNORECASE), ("Samsung", "Galaxy")),
    (re.compile(r"pixel", re.IGNORECASE), ("Google", "Pixel")),
)


class MikrotikRouterError(Exception):
    """Base RouterOS client error."""


class MikrotikAuthError(MikrotikRouterError):
    """Authentication failed."""


class MikrotikConnectionError(MikrotikRouterError):
    """Network or protocol error."""


class MikrotikUnsupportedError(MikrotikRouterError):
    """RouterOS feature or version is unsupported."""


class MikrotikRouterOSClient:
    """Blocking RouterOS client wrapped for Home Assistant."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        username: str,
        password: str,
        port: int,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._hass = hass
        self._host = host
        self._username = username
        self._password = password
        self._port = port
        self._timeout = timeout

    @property
    def address(self) -> str:
        return f"{self._host}:{self._port}"

    async def async_discover(self) -> RouterDiscoveryData:
        """Fetch router metadata, DHCP hostnames, and the current registration table."""
        return await self._hass.async_add_executor_job(self._discover_sync)

    async def async_fetch_registration_table(self) -> dict[str, RegistrationEntry]:
        """Fetch the RouterOS WiFi registration table."""
        return await self._hass.async_add_executor_job(self._fetch_registration_table_sync)

    async def async_close(self) -> None:
        """Close resources held by the client."""
        return None

    def _discover_sync(self) -> RouterDiscoveryData:
        try:
            with routeros.dial(
                self.address,
                self._username,
                self._password,
                timeout=self._timeout,
                logger=LOGGER,
            ) as connection:
                identity = self._first_row(
                    self._run_command(connection.run, SYSTEM_IDENTITY_PATH)
                )
                resource = self._first_row(
                    self._run_command(connection.run, SYSTEM_RESOURCE_PATH)
                )
                routerboard = self._safe_first_row(
                    connection.run, SYSTEM_ROUTERBOARD_PATH
                )
                license_data = self._safe_first_row(connection.run, SYSTEM_LICENSE_PATH)
                registration_rows = self._run_command(
                    connection.run, REGISTRATION_TABLE_PATH
                )
                dhcp_rows = self._safe_run_rows(connection.run, DHCP_LEASES_PATH)
        except routeros.LoginError as err:
            raise MikrotikAuthError(str(err)) from err
        except OSError as err:
            raise MikrotikConnectionError(str(err)) from err
        except routeros.DeviceError as err:
            self._raise_for_device_error(err)
        except routeros.RouterOSError as err:
            raise MikrotikConnectionError(str(err)) from err

        router_info = self._build_router_info(
            identity=identity,
            resource=resource,
            routerboard=routerboard,
            license_data=license_data,
        )
        registrations = self._parse_registration_rows(registration_rows)
        dhcp_hostnames = self._parse_dhcp_rows(dhcp_rows)
        return RouterDiscoveryData(
            router_info=router_info,
            registrations=registrations,
            dhcp_hostnames=dhcp_hostnames,
        )

    def _fetch_registration_table_sync(self) -> dict[str, RegistrationEntry]:
        try:
            with routeros.dial(
                self.address,
                self._username,
                self._password,
                timeout=self._timeout,
                logger=LOGGER,
            ) as connection:
                rows = self._run_command(connection.run, REGISTRATION_TABLE_PATH)
        except routeros.LoginError as err:
            raise MikrotikAuthError(str(err)) from err
        except OSError as err:
            raise MikrotikConnectionError(str(err)) from err
        except routeros.DeviceError as err:
            self._raise_for_device_error(err)
        except routeros.RouterOSError as err:
            raise MikrotikConnectionError(str(err)) from err

        return self._parse_registration_rows(rows)

    def _raise_for_device_error(self, err: routeros.DeviceError) -> None:
        message = str(err).lower()
        if "no such command" in message or "bad command name" in message:
            raise MikrotikUnsupportedError(str(err)) from err
        raise MikrotikConnectionError(str(err)) from err

    def _run_command(
        self, command: Callable[..., Any], path: str
    ) -> list[dict[str, str]]:
        reply = command(path)
        return [dict(sentence.map) for sentence in reply.re]

    def _safe_run_rows(
        self, command: Callable[..., Any], path: str
    ) -> list[dict[str, str]]:
        try:
            return self._run_command(command, path)
        except routeros.DeviceError:
            return []

    def _safe_first_row(
        self, command: Callable[..., Any], path: str
    ) -> dict[str, str]:
        rows = self._safe_run_rows(command, path)
        return self._first_row(rows)

    def _first_row(self, rows: list[dict[str, str]]) -> dict[str, str]:
        if not rows:
            return {}
        return rows[0]

    def _build_router_info(
        self,
        *,
        identity: dict[str, str],
        resource: dict[str, str],
        routerboard: dict[str, str],
        license_data: dict[str, str],
    ) -> RouterInfo:
        version = resource.get("version")
        if version is None or not version.startswith(SUPPORTED_ROUTEROS_MAJOR):
            raise MikrotikUnsupportedError(
                "Only RouterOS 7.x with the WiFi package is supported"
            )

        serial_number = routerboard.get("serial-number")
        software_id = license_data.get("software-id")
        unique_id = serial_number or software_id or identity.get("name") or self.address

        return RouterInfo(
            unique_id=unique_id,
            identity=identity.get("name", self._host),
            version=version,
            board_name=resource.get("board-name") or routerboard.get("model"),
            serial_number=serial_number,
            software_id=software_id,
        )

    def _parse_dhcp_rows(self, rows: list[dict[str, str]]) -> dict[str, str]:
        dhcp_hostnames: dict[str, str] = {}
        for row in rows:
            mac_address = row.get("mac-address")
            hostname = row.get("host-name") or row.get("client-hostname")
            if not mac_address or not hostname:
                continue
            dhcp_hostnames[format_mac(mac_address)] = hostname
        return dhcp_hostnames

    def _parse_registration_rows(
        self, rows: list[dict[str, str]]
    ) -> dict[str, RegistrationEntry]:
        registrations: dict[str, RegistrationEntry] = {}
        for row in rows:
            mac_address_raw = row.get("mac-address")
            if not mac_address_raw:
                continue

            mac_address = format_mac(mac_address_raw)
            hostname = row.get("host-name") or row.get("hostname")
            registrations[mac_address] = RegistrationEntry(
                mac_address=mac_address,
                hostname=hostname,
                ip_address=row.get("last-ip") or row.get("ip-address"),
                ssid=row.get("ssid"),
                interface=row.get("interface"),
                signal_dbm=_parse_dbm(row.get("signal")),
                tx_rate_mbps=_coalesce_rate(
                    row.get("tx-rate"),
                    row.get("tx-bits-per-second"),
                ),
                rx_rate_mbps=_coalesce_rate(
                    row.get("rx-rate"),
                    row.get("rx-bits-per-second"),
                ),
                uptime=_parse_duration(row.get("uptime")),
                last_activity=_parse_duration(row.get("last-activity")),
                band=row.get("band"),
                auth_type=row.get("auth-type"),
                raw=row,
            )
        return registrations


def infer_manufacturer_model(
    registration_name: str | None, dhcp_name: str | None
) -> tuple[str | None, str | None]:
    """Infer manufacturer/model from visible names when possible."""
    for candidate in (registration_name, dhcp_name):
        if not candidate:
            continue
        for pattern, details in _MODEL_PATTERNS:
            if pattern.search(candidate):
                return details
    return None, None


def resolve_client_name(
    mac_address: str,
    registration_name: str | None,
    dhcp_hostnames: dict[str, str],
) -> str:
    """Resolve the Home Assistant device name."""
    return registration_name or dhcp_hostnames.get(mac_address) or mac_address


def _parse_rate_mbps(value: str | None) -> float | None:
    if not value:
        return None

    normalized = value.strip().lower().replace(" ", "")
    if normalized.isdigit():
        return round(int(normalized) / 1_000_000, 2)

    match = _RATE_RE.search(normalized)
    if match is None:
        return None

    rate = float(match.group(1))
    unit_prefix = match.group(2).lower()

    if "mbps" in normalized or "mbit/s" in normalized:
        return round(rate, 2)
    if "gbps" in normalized or "gbit/s" in normalized:
        return round(rate * 1000, 2)
    if "kbps" in normalized or "kbit/s" in normalized:
        return round(rate / 1000, 2)
    if "bps" in normalized or "bit/s" in normalized:
        return round(rate / 1_000_000, 2)

    if unit_prefix == "g":
        return round(rate * 1000, 2)
    if unit_prefix == "m":
        return round(rate, 2)
    if unit_prefix == "k":
        return round(rate / 1000, 2)

    return round(rate, 2)


def _coalesce_rate(primary: str | None, fallback: str | None) -> float | None:
    primary_rate = _parse_rate_mbps(primary)
    if primary_rate not in (None, 0):
        return primary_rate

    fallback_rate = _parse_rate_mbps(fallback)
    if fallback_rate is not None:
        return fallback_rate

    return primary_rate


def _parse_dbm(value: str | None) -> int | None:
    if not value:
        return None
    match = _DBM_RE.search(value)
    if match is None:
        return None
    return int(match.group(1))


def _parse_duration(value: str | None) -> timedelta | None:
    if not value:
        return None
    try:
        return routeros.cast(value, timedelta)
    except ValueError:
        return None
