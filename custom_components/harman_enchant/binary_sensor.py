# SPDX-License-Identifier: AGPL-3.0-only
"""Binary sensors of the Harman Kardon Enchant integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import FEATURE_TV_AUDIO
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors the speaker supports."""
    coordinator = entry.runtime_data
    if coordinator.has_feature(FEATURE_TV_AUDIO) and coordinator.supports("getStreamingStatus"):
        async_add_entities([DolbyAtmosBinarySensor(coordinator)])


class DolbyAtmosBinarySensor(EnchantEntity, BinarySensorEntity):
    """On while Dolby Atmos audio is playing."""

    _attr_translation_key = "dolby_atmos"

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "dolby_atmos")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.is_atmos
