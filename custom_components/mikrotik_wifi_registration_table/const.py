from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "mikrotik_wifi_registration_table"
NAME: Final = "MikroTik WiFi Registration Table"

PLATFORMS: Final[list[Platform]] = [Platform.SENSOR, Platform.DEVICE_TRACKER]

CONF_GRACE_PERIOD: Final = "grace_period"
CONF_MANUAL_MAC: Final = "manual_mac"
CONF_MANUAL_NAME: Final = "manual_name"
CONF_POLL_INTERVAL: Final = "poll_interval"
CONF_ROUTER_ID: Final = "router_id"
CONF_ROUTER_NAME: Final = "router_name"
CONF_TRACKED_DEVICES: Final = "tracked_devices"

DEFAULT_GRACE_PERIOD: Final = 30
DEFAULT_POLL_INTERVAL: Final = 15
DEFAULT_PORT: Final = 8728
DEFAULT_TIMEOUT: Final = 10.0

MIN_GRACE_PERIOD: Final = 0
MIN_POLL_INTERVAL: Final = 5

REGISTRATION_TABLE_PATH: Final = "/interface/wifi/registration-table/print"
DHCP_LEASES_PATH: Final = "/ip/dhcp-server/lease/print"
SYSTEM_IDENTITY_PATH: Final = "/system/identity/print"
SYSTEM_RESOURCE_PATH: Final = "/system/resource/print"
SYSTEM_ROUTERBOARD_PATH: Final = "/system/routerboard/print"
SYSTEM_LICENSE_PATH: Final = "/system/license/print"

SUPPORTED_ROUTEROS_MAJOR: Final = "7."

PRESENCE_TRACKER_SUFFIX: Final = "presence"
DEVICE_NAME_KEY: Final = "name"
DEVICE_MANUFACTURER_KEY: Final = "manufacturer"
DEVICE_MODEL_KEY: Final = "model"

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_POLL_INTERVAL)
