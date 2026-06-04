# MikroTik WiFi Registration Table

Home Assistant custom integration for presence detection based on the MikroTik RouterOS 7 WiFi registration table.

Author: Wojciech Jablonski <wjablonski90@gmail.com>

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/Y0U720SE9I)

## Overview

This integration reads `/interface/wifi/registration-table/print` from MikroTik RouterOS 7 and uses it as the source of truth for WiFi presence.

If a client MAC is present in the registration table, the device is considered `home`.
If the MAC disappears, the device tracker stays `home` only for the configured grace period and then changes to `not_home`.

This approach is especially useful for Apple devices, which often behave poorly with presence methods based on:

- DHCP leases
- ARP tables
- ICMP ping
- generic host-tracking logic

## Features

- Home Assistant UI setup through Config Flow
- Presence based on the actual MikroTik WiFi registration table
- One Home Assistant device per tracked client
- Presence entity plus WiFi telemetry sensors for each tracked client
- Add more devices later without removing and re-adding the integration
- Optional manual add for offline clients by MAC address
- Diagnostics support with secret redaction
- HACS-compatible repository layout

## Requirements

- Home Assistant with support for custom integrations
- MikroTik RouterOS 7.x
- MikroTik `wifi` package with `/interface/wifi/registration-table`
- RouterOS API enabled, usually on port `8728`
- A RouterOS user with read access to:
  - `/interface/wifi/registration-table`
  - `/system/*`
  - `/ip/dhcp-server/lease` (optional, only used for hostname fallback)

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Go to `Integrations`.
3. Open the menu and choose `Custom repositories`.
4. Add this repository URL:

```text
https://github.com/wjablonski90/ha-mikrotik-wifi-reg-table
```

5. Select repository type: `Integration`.
6. Install `MikroTik WiFi Registration Table`.
7. Restart Home Assistant.

### Manual

1. Copy the folder below into your Home Assistant `custom_components` directory:

```text
custom_components/mikrotik_wifi_registration_table
```

2. Restart Home Assistant.

## Setup

1. In Home Assistant, go to `Settings -> Devices & services`.
2. Click `Add integration`.
3. Search for `MikroTik WiFi Registration Table`.
4. Enter:
   - host
   - username
   - password
   - port
   - poll interval
5. After the router connection succeeds, select the WiFi clients you want to track.

## Adding More Devices Later

You do not need to remove the integration.

1. Go to `Settings -> Devices & services`.
2. Open `MikroTik WiFi Registration Table`.
3. Click `Configure`.
4. Add more visible WiFi clients from `Tracked devices`.
5. If a client is currently offline, you can also add it manually with:
   - `Manual MAC address`
   - `Manual friendly name`

Saving the options reloads the integration and creates entities for newly tracked devices automatically.

## Entities

For each tracked client the integration creates:

- `device_tracker.<device_name>_presence`
- `sensor.<device_name>_signal`
- `sensor.<device_name>_tx_rate`
- `sensor.<device_name>_rx_rate`
- `sensor.<device_name>_uptime`
- `sensor.<device_name>_last_activity`
- `sensor.<device_name>_ssid`
- `sensor.<device_name>_band`
- `sensor.<device_name>_auth_type`

Example:

- `device_tracker.iphone_wojciech_presence`
- `sensor.iphone_wojciech_signal`
- `sensor.iphone_wojciech_ssid`

## Presence Logic

- `home`: the device MAC is present in `/interface/wifi/registration-table`
- `not_home`: the MAC is missing and the grace period has expired

Default grace period:

- `30` seconds

## Naming

Default tracked device naming priority:

1. RouterOS registration table hostname
2. DHCP hostname
3. MAC address

Entity IDs are suggested from the tracked device name, for example:

- `device_tracker.iphone_wojciech_presence`

You can still rename devices and entities later from the Home Assistant UI.

## Sensor Notes

- `tx_rate` and `rx_rate` are normalized to `Mbit/s`
- negotiated WiFi link rate is preferred over raw throughput values
- `uptime` is presented in a human-friendly format such as `2d 3h 14m`

## Device Model in Home Assistant

Each tracked client is registered as its own Home Assistant device using this integration's own identifier based on MAC address.

The integration does not publish the client MAC as a shared Home Assistant device connection. This helps prevent unrelated entities from other integrations from being merged into the same Home Assistant device.

## Diagnostics

Diagnostics include:

- RouterOS version
- poll interval
- number of tracked devices
- number of currently connected devices

Sensitive data such as passwords is redacted automatically.

## Troubleshooting

### Presence entity is unavailable

Check the following:

- the client was added to the integration
- the RouterOS API is reachable from Home Assistant
- the MAC really appears in the MikroTik WiFi registration table
- Home Assistant was restarted after updating the custom integration

### A device does not appear in the picker

Only clients visible to `/interface/wifi/registration-table` can be selected automatically.

If the device is currently offline, add it manually with:

- `Manual MAC address`
- `Manual friendly name`

### Apple devices still look unreliable

This integration only tracks actual WiFi association on MikroTik.

If an iPhone disconnects from WiFi because the user left home, presence changes quickly.
If an iPhone goes idle but remains associated, presence stays `home`, which is usually the desired behavior for home WiFi presence.

## Support

- Issues: https://github.com/wjablonski90/ha-mikrotik-wifi-reg-table/issues
- Repository: https://github.com/wjablonski90/ha-mikrotik-wifi-reg-table
