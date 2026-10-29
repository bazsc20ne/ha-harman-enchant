# SPDX-License-Identifier: AGPL-3.0-only
"""Buttons of the Harman Kardon Enchant integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FEATURE_CALIBRATE, FEATURE_MOMENT
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the buttons the product handles."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    if coordinator.has_feature(FEATURE_CALIBRATE):
        entities.append(CalibrateButton(coordinator))
    if coordinator.has_feature(FEATURE_MOMENT):
        entities.append(MomentButton(coordinator))
    async_add_entities(entities)


class CalibrateButton(EnchantEntity, ButtonEntity):
    """Start the sound calibration, like the CALIBRATION key of the remote control."""

    _attr_translation_key = "calibrate"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "calibrate")

    async def async_press(self) -> None:
        await self.coordinator.async_write("sendAppController", {"key_pressed": "calibration"})


class MomentButton(EnchantEntity, ButtonEntity):
    """Start or stop the Moment set up in the vendor app, like the Moment key of the speaker."""

    _attr_translation_key = "moment"

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "moment")

    async def async_press(self) -> None:
        await self.coordinator.async_write("sendAppController", {"key_pressed": "smart_triger"})
