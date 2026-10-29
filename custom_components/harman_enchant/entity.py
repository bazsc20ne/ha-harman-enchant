# SPDX-License-Identifier: AGPL-3.0-only
"""Base entity of the Harman Kardon Enchant integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import EnchantCoordinator


class EnchantEntity(CoordinatorEntity[EnchantCoordinator]):
    """An entity that belongs to one speaker."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EnchantCoordinator, key: str) -> None:
        super().__init__(coordinator)
        info = coordinator.device_info
        status = coordinator.status
        mac = format_mac(info.get("wlan0_mac") or status.get("MAC") or coordinator.client.host)
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_NETWORK_MAC, mac)},
            manufacturer=MANUFACTURER,
            model=status.get("hm_product_name"),
            name=info.get("name") or status.get("hm_product_name"),
            serial_number=status.get("hm_sn") or info.get("serial_number"),
            sw_version=info.get("firmware") or status.get("firmware"),
        )
