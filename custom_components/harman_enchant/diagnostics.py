# SPDX-License-Identifier: AGPL-3.0-only
"""Diagnostics of the Harman Kardon Enchant integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import CONF_CERTIFICATE
from .coordinator import EnchantConfigEntry

TO_REDACT = {
    CONF_CERTIFICATE,
    CONF_HOST,
    "BT_MAC",
    "DeviceName",
    "GroupName",
    "MAC",
    "apcli0",
    "essid",
    "eth2",
    "friendly_name",
    "group_id",
    "hm_sn",
    "id",
    "mac",
    "mac_crc",
    "name",
    "online_devices",
    "p2p_mac",
    "ra0",
    "serial_number",
    "ssid",
    "temp_uuid",
    "upnp_uuid",
    "user1",
    "user2",
    "uuid",
    "wlan0_mac",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EnchantConfigEntry) -> dict[str, Any]:
    """Return redacted data about the speaker."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is None:
        # Not set up, e.g. because the speaker's certificate changed.
        return async_redact_data({"entry": dict(entry.data), "state": entry.state.value}, TO_REDACT)
    return async_redact_data(
        {
            "entry": dict(entry.data),
            "device_info": coordinator.device_info,
            "status": coordinator.status,
            "answers": coordinator.data.answers,
            "stream_info": coordinator.data.stream_info,
            "unsupported_commands": sorted(coordinator.unsupported),
        },
        TO_REDACT,
    )
