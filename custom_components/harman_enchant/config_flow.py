# SPDX-License-Identifier: AGPL-3.0-only
"""Config flow of the Harman Kardon Enchant integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
import voluptuous as vol

from .api import KIND_SUB, EnchantClient, EnchantError, create_ssl_context, device_kind, fetch_server_certificate
from .const import CONF_CERTIFICATE, DOMAIN


class NotEnchant(Exception):
    """The device answered, but it is not an Enchant speaker."""


class SubViaSoundbar(Exception):
    """An Enchant Sub works only through the soundbar it is paired with."""


class EnchantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add an Enchant speaker."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._name: str | None = None
        self._certificate: str | None = None

    async def _async_identify(self, host: str) -> tuple[str, str, str]:
        """Return (mac, name, server certificate) of the speaker at host."""
        unchecked = await self.hass.async_add_executor_job(create_ssl_context)
        certificate = await fetch_server_certificate(host, unchecked)
        # Identify the speaker with the certificate just read, as later connections will.
        ssl_context = await self.hass.async_add_executor_job(create_ssl_context, certificate)
        client = EnchantClient(host, async_get_clientsession(self.hass), ssl_context)
        device = (await client.command("getDeviceInfo")).get("device_info") or {}
        status = await client.command("getStatusEx")
        product = str(status.get("hm_product_name") or "")
        kind = device_kind(product)
        if kind is None:
            raise NotEnchant(product)
        if kind == KIND_SUB:
            raise SubViaSoundbar(product)
        mac = device.get("wlan0_mac") or status.get("MAC")
        if not mac:
            raise NotEnchant(product)
        return format_mac(mac), str(device.get("name") or product), certificate

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                mac, name, certificate = await self._async_identify(host)
            except NotEnchant:
                errors["base"] = "not_enchant"
            except SubViaSoundbar:
                errors["base"] = "sub_via_soundbar"
            except EnchantError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(title=name, data={CONF_HOST: host, CONF_CERTIFICATE: certificate})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}),
            errors=errors,
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        host = discovery_info.host
        mac = discovery_info.properties.get("MAC") or discovery_info.properties.get("mac")
        if mac:
            await self.async_set_unique_id(format_mac(mac))
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        try:
            mac, name, certificate = await self._async_identify(host)
        except NotEnchant:
            return self.async_abort(reason="not_enchant")
        except SubViaSoundbar:
            return self.async_abort(reason="sub_via_soundbar")
        except EnchantError:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._host = host
        self._name = name
        self._certificate = certificate
        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._name or "", data={CONF_HOST: self._host, CONF_CERTIFICATE: self._certificate}
            )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={"name": self._name or "", "host": self._host or ""},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The speaker presented another certificate than the one recorded at setup."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        host = entry.data[CONF_HOST]
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                mac, _name, certificate = await self._async_identify(host)
            except (NotEnchant, SubViaSoundbar):
                errors["base"] = "not_enchant"
            except EnchantError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates={CONF_CERTIFICATE: certificate})
        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"name": entry.title, "host": host},
            errors=errors,
        )
