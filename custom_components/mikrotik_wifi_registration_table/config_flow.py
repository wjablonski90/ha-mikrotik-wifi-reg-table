from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.device_registry import format_mac
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_GRACE_PERIOD,
    CONF_MANUAL_MAC,
    CONF_MANUAL_NAME,
    CONF_POLL_INTERVAL,
    CONF_ROUTER_ID,
    CONF_ROUTER_NAME,
    CONF_TRACKED_DEVICES,
    DEFAULT_GRACE_PERIOD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEVICE_MANUFACTURER_KEY,
    DEVICE_MODEL_KEY,
    DEVICE_NAME_KEY,
    DOMAIN,
    MIN_GRACE_PERIOD,
    MIN_POLL_INTERVAL,
)
from .models import RegistrationEntry, RouterDiscoveryData, TrackedDevicePayload
from .routeros_client import (
    MikrotikAuthError,
    MikrotikConnectionError,
    MikrotikRouterOSClient,
    MikrotikUnsupportedError,
    infer_manufacturer_model,
    resolve_client_name,
)


class MikrotikWifiRegistrationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for MikroTik WiFi Registration Table."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._discovery: RouterDiscoveryData | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return MikrotikWifiRegistrationOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                discovery = await self._async_discover(user_input)
            except MikrotikAuthError:
                errors["base"] = "invalid_auth"
            except MikrotikUnsupportedError:
                errors["base"] = "unsupported_router"
            except MikrotikConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                if not discovery.registrations:
                    errors["base"] = "no_devices_found"
                else:
                    self._user_input = dict(user_input)
                    self._discovery = discovery
                    await self.async_set_unique_id(discovery.router_info.unique_id)
                    self._abort_if_unique_id_configured(
                        updates={
                            CONF_HOST: user_input[CONF_HOST],
                            CONF_PORT: user_input[CONF_PORT],
                            CONF_USERNAME: user_input[CONF_USERNAME],
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                        }
                    )
                    return await self.async_step_select_devices()

        return self.async_show_form(
            step_id="user",
            data_schema=self._build_user_schema(user_input),
            errors=errors,
        )

    async def async_step_select_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if self._discovery is None:
            return await self.async_step_user()

        if user_input is not None:
            selected_macs = user_input[CONF_TRACKED_DEVICES]
            if not selected_macs:
                errors["base"] = "no_devices_selected"
            else:
                tracked_devices = self._build_tracked_payloads(
                    selected_macs,
                    self._discovery.registrations,
                    self._discovery.dhcp_hostnames,
                )
                return self.async_create_entry(
                    title=self._discovery.router_info.identity,
                    data={
                        CONF_HOST: self._user_input[CONF_HOST],
                        CONF_PORT: self._user_input[CONF_PORT],
                        CONF_USERNAME: self._user_input[CONF_USERNAME],
                        CONF_PASSWORD: self._user_input[CONF_PASSWORD],
                        CONF_ROUTER_ID: self._discovery.router_info.unique_id,
                        CONF_ROUTER_NAME: self._discovery.router_info.identity,
                    },
                    options={
                        CONF_POLL_INTERVAL: self._user_input[CONF_POLL_INTERVAL],
                        CONF_GRACE_PERIOD: DEFAULT_GRACE_PERIOD,
                        CONF_TRACKED_DEVICES: tracked_devices,
                    },
                )

        return self.async_show_form(
            step_id="select_devices",
            data_schema=self._build_device_schema(
                self._discovery.registrations,
                self._discovery.dhcp_hostnames,
            ),
            errors=errors,
        )

    async def _async_discover(
        self, values: Mapping[str, Any]
    ) -> RouterDiscoveryData:
        client = MikrotikRouterOSClient(
            self.hass,
            host=values[CONF_HOST],
            username=values[CONF_USERNAME],
            password=values[CONF_PASSWORD],
            port=values[CONF_PORT],
        )
        return await client.async_discover()

    def _build_user_schema(
        self, user_input: Mapping[str, Any] | None
    ) -> vol.Schema:
        user_input = user_input or self._user_input
        return vol.Schema(
            {
                vol.Required(
                    CONF_HOST, default=user_input.get(CONF_HOST, "")
                ): str,
                vol.Required(
                    CONF_USERNAME, default=user_input.get(CONF_USERNAME, "")
                ): str,
                vol.Required(
                    CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, "")
                ): str,
                vol.Required(
                    CONF_PORT, default=user_input.get(CONF_PORT, DEFAULT_PORT)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=user_input.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL)),
            }
        )

    def _build_device_schema(
        self,
        registrations: dict[str, RegistrationEntry],
        dhcp_hostnames: dict[str, str],
        selected_macs: list[str] | None = None,
    ) -> vol.Schema:
        options = {
            mac_address: _build_device_label(entry, dhcp_hostnames)
            for mac_address, entry in registrations.items()
        }
        return vol.Schema(
            {
                vol.Required(
                    CONF_TRACKED_DEVICES, default=selected_macs or []
                ): cv.multi_select(options)
            }
        )

    def _build_tracked_payloads(
        self,
        selected_macs: list[str],
        registrations: dict[str, RegistrationEntry],
        dhcp_hostnames: dict[str, str],
    ) -> dict[str, dict[str, str | None]]:
        tracked_devices: dict[str, dict[str, str | None]] = {}
        for raw_mac in selected_macs:
            mac_address = format_mac(raw_mac)
            entry = registrations.get(mac_address)
            registration_name = entry.hostname if entry is not None else None
            name = resolve_client_name(mac_address, registration_name, dhcp_hostnames)
            manufacturer, model = infer_manufacturer_model(
                registration_name, dhcp_hostnames.get(mac_address)
            )
            tracked_devices[mac_address] = TrackedDevicePayload(
                name=name,
                manufacturer=manufacturer,
                model=model,
            ).as_dict()
        return tracked_devices


class MikrotikWifiRegistrationOptionsFlow(config_entries.OptionsFlow):
    """Options flow for MikroTik WiFi Registration Table."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        discovery: RouterDiscoveryData | None = None

        try:
            discovery = await self._async_discover()
        except MikrotikAuthError:
            errors["base"] = "invalid_auth"
        except MikrotikUnsupportedError:
            errors["base"] = "unsupported_router"
        except MikrotikConnectionError:
            errors["base"] = "cannot_connect"
        except Exception:
            errors["base"] = "unknown"

        if user_input is not None:
            selected_macs = list(user_input[CONF_TRACKED_DEVICES])
            manual_mac = user_input.get(CONF_MANUAL_MAC, "").strip()
            manual_name = user_input.get(CONF_MANUAL_NAME, "").strip()

            if manual_mac:
                try:
                    selected_macs.append(format_mac(manual_mac))
                except ValueError:
                    errors["base"] = "invalid_mac"

            if not selected_macs:
                errors["base"] = "no_devices_selected"
            elif not errors:
                tracked_devices = self._build_tracked_payloads(
                    selected_macs,
                    discovery.registrations if discovery is not None else {},
                    discovery.dhcp_hostnames if discovery is not None else {},
                    manual_name_overrides={
                        format_mac(manual_mac): manual_name
                    }
                    if manual_mac and manual_name
                    else None,
                )
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                        CONF_GRACE_PERIOD: user_input[CONF_GRACE_PERIOD],
                        CONF_TRACKED_DEVICES: tracked_devices,
                    },
                )

        return self.async_show_form(
            step_id="init",
            data_schema=self._build_options_schema(discovery),
            errors=errors,
        )

    async def _async_discover(self) -> RouterDiscoveryData:
        client = MikrotikRouterOSClient(
            self.hass,
            host=self._config_entry.data[CONF_HOST],
            username=self._config_entry.data[CONF_USERNAME],
            password=self._config_entry.data[CONF_PASSWORD],
            port=self._config_entry.data[CONF_PORT],
        )
        return await client.async_discover()

    def _build_options_schema(self, discovery: RouterDiscoveryData | None) -> vol.Schema:
        tracked_devices = self._config_entry.options.get(CONF_TRACKED_DEVICES, {})
        options = dict(tracked_devices)

        current_registrations = discovery.registrations if discovery is not None else {}
        dhcp_hostnames = discovery.dhcp_hostnames if discovery is not None else {}
        labels: dict[str, str] = {}

        for mac_address, payload in options.items():
            labels[mac_address] = payload.get(DEVICE_NAME_KEY, mac_address)

        for mac_address, entry in current_registrations.items():
            labels[mac_address] = _build_device_label(entry, dhcp_hostnames)

        selected = list(tracked_devices)
        return vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=self._config_entry.options.get(
                        CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_POLL_INTERVAL)),
                vol.Required(
                    CONF_GRACE_PERIOD,
                    default=self._config_entry.options.get(
                        CONF_GRACE_PERIOD, DEFAULT_GRACE_PERIOD
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_GRACE_PERIOD)),
                vol.Required(
                    CONF_TRACKED_DEVICES, default=selected
                ): cv.multi_select(labels),
                vol.Optional(CONF_MANUAL_MAC, default=""): str,
                vol.Optional(CONF_MANUAL_NAME, default=""): str,
            }
        )

    def _build_tracked_payloads(
        self,
        selected_macs: list[str],
        registrations: dict[str, RegistrationEntry],
        dhcp_hostnames: dict[str, str],
        manual_name_overrides: dict[str, str] | None = None,
    ) -> dict[str, dict[str, str | None]]:
        existing_devices = self._config_entry.options.get(CONF_TRACKED_DEVICES, {})
        tracked_devices: dict[str, dict[str, str | None]] = {}
        manual_name_overrides = manual_name_overrides or {}

        for raw_mac in selected_macs:
            mac_address = format_mac(raw_mac)
            entry = registrations.get(mac_address)
            if entry is None and mac_address in existing_devices:
                tracked_devices[mac_address] = {
                    **existing_devices[mac_address],
                    **(
                        {DEVICE_NAME_KEY: manual_name_overrides[mac_address]}
                        if mac_address in manual_name_overrides
                        else {}
                    ),
                }
                continue

            if entry is None and mac_address in manual_name_overrides:
                manufacturer, model = infer_manufacturer_model(
                    manual_name_overrides[mac_address], None
                )
                tracked_devices[mac_address] = {
                    DEVICE_NAME_KEY: manual_name_overrides[mac_address],
                    DEVICE_MANUFACTURER_KEY: manufacturer,
                    DEVICE_MODEL_KEY: model,
                }
                continue

            registration_name = entry.hostname if entry is not None else None
            name = manual_name_overrides.get(mac_address) or resolve_client_name(
                mac_address, registration_name, dhcp_hostnames
            )
            manufacturer, model = infer_manufacturer_model(
                manual_name_overrides.get(mac_address) or registration_name,
                dhcp_hostnames.get(mac_address),
            )
            tracked_devices[mac_address] = {
                DEVICE_NAME_KEY: name,
                DEVICE_MANUFACTURER_KEY: manufacturer,
                DEVICE_MODEL_KEY: model,
            }

        return tracked_devices


def _build_device_label(
    entry: RegistrationEntry, dhcp_hostnames: dict[str, str]
) -> str:
    name = resolve_client_name(entry.mac_address, entry.hostname, dhcp_hostnames)
    ssid = entry.ssid or "unknown SSID"
    return f"{name} ({entry.mac_address}, {ssid})"
