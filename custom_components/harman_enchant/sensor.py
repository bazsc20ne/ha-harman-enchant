# SPDX-License-Identifier: AGPL-3.0-only
"""Sensors of the Harman Kardon Enchant integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PLAYING_SOURCE_OPTIONS, playing_source_key
from .const import FEATURE_SLEEP_TIMER, FEATURE_SURROUND_LAYOUT, FEATURE_TV_AUDIO
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors the speaker supports."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    if coordinator.has_feature(FEATURE_TV_AUDIO):
        entities.append(AudioFormatSensor(coordinator))
    if coordinator.supports("getStreamingStatus"):
        entities.append(PlayingSourceSensor(coordinator))
    if coordinator.offers(FEATURE_SLEEP_TIMER, "getSleepTimer", "remain_time"):
        entities.append(SleepTimerRemainingSensor(coordinator))
    if coordinator.has_feature(FEATURE_SURROUND_LAYOUT) and coordinator.supports("getGroupInfo"):
        entities.append(SurroundLayoutSensor(coordinator))
    async_add_entities(entities)


class AudioFormatSensor(EnchantEntity, SensorEntity):
    """Format of the audio arriving from the TV, e.g. Dolby Atmos / 12ch / 48 kHz."""

    _attr_translation_key = "audio_format"

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "audio_format")

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.audio_format

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        info = self.coordinator.data.stream_info
        return dict(info) if info else None


class PlayingSourceSensor(EnchantEntity, SensorEntity):
    """What the speaker is playing right now (input or streaming service)."""

    _attr_translation_key = "playing_source"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PLAYING_SOURCE_OPTIONS

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "playing_source")

    @property
    def native_value(self) -> str | None:
        return playing_source_key(self.coordinator.data.playing_source)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source_name": self.coordinator.data.playing_source}


class SleepTimerRemainingSensor(EnchantEntity, SensorEntity):
    """Time left until the sleep timer switches the speaker off."""

    _attr_translation_key = "sleep_timer_remaining"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "sleep_timer_remaining")

    @property
    def native_value(self) -> int | None:
        value = self.coordinator.data.value("getSleepTimer", "remain_time")
        try:
            return round(int(value) / 60)
        except (TypeError, ValueError):
            return None


# Icon per layout. These cannot live in icons.json: its state keys may not contain dots.
LAYOUT_ICONS = {
    "2.0": "mdi:surround-sound-2-0",
    "2.1": "mdi:surround-sound-2-1",
    "3.1": "mdi:surround-sound-3-1",
    "3.1.2": "mdi:surround-sound-3-1",
    "3.1.4": "mdi:surround-sound-3-1",
    "5.1": "mdi:surround-sound-5-1",
    "5.1.2": "mdi:surround-sound-5-1-2",
    "5.1.4": "mdi:surround-sound-5-1",
    "7.1": "mdi:surround-sound-7-1",
    "7.1.2": "mdi:surround-sound-7-1",
    "7.1.4": "mdi:surround-sound-7-1",
}


class SurroundLayoutSensor(EnchantEntity, SensorEntity):
    """Channel layout of the speaker group, e.g. 7.1.4, with its members."""

    _attr_translation_key = "surround_layout"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "surround_layout")

    @property
    def native_value(self) -> str | None:
        group = self.coordinator.data.group
        return group.layout if group else None

    @property
    def icon(self) -> str | None:
        return LAYOUT_ICONS.get(self.native_value or "")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        group = self.coordinator.data.group
        if not group:
            return None
        return {
            "members": [
                {"model": m.device_name, "name": m.friendly_name, "channels": m.channels} for m in group.members
            ]
        }
