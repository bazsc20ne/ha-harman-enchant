# SPDX-License-Identifier: AGPL-3.0-only
"""The Harman Kardon Enchant integration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.components.network import async_get_source_ip
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import EnchantClient, EnchantError, create_ssl_context
from .const import DOMAIN
from .coordinator import EnchantConfigEntry, EnchantCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_FILE = Path(__file__).parent / "frontend" / "harman-enchant-card.js"
CARD_URL = f"/{DOMAIN}/harman-enchant-card.js"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card and load it on every dashboard."""
    content = await hass.async_add_executor_job(CARD_FILE.read_bytes)
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={hashlib.sha256(content).hexdigest()[:8]}")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: EnchantConfigEntry) -> bool:
    """Set up one speaker."""
    host = entry.data[CONF_HOST]
    ssl_context = await hass.async_add_executor_job(create_ssl_context)
    client = EnchantClient(host, async_get_clientsession(hass), ssl_context)
    try:
        device_info = (await client.command("getDeviceInfo")).get("device_info") or {}
        status = await client.command("getStatusEx")
    except EnchantError as err:
        raise ConfigEntryNotReady(f"{host} is not reachable: {err}") from err

    coordinator = EnchantCoordinator(hass, entry, client, device_info, status)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    try:
        source_ip = await async_get_source_ip(hass, target_ip=host)
        await coordinator.async_start_events(source_ip)
    except (OSError, EnchantError) as err:
        _LOGGER.warning("Event notifications from %s are not available: %s", host, err)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnchantConfigEntry) -> bool:
    """Unload a speaker."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
