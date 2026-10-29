# SPDX-License-Identifier: AGPL-3.0-only
"""Number settings of the Harman Kardon Enchant integration."""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfSoundPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import build_eq_band_payload, find_custom_eq, format_frequency
from .const import (
    AUDIO_SYNC_MAX_MS,
    EQ_GAIN_MAX,
    EQ_GAIN_MIN,
    EQ_GAIN_STEP,
    FEATURE_AUDIO_SYNC,
    FEATURE_EQUALIZER,
    FEATURE_SLEEP_TIMER,
    SLEEP_TIMER_MAX_MIN,
)
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the number settings the speaker supports."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    if coordinator.offers(FEATURE_AUDIO_SYNC, "getAudioSync", "audio_sync"):
        entities.append(AudioSyncNumber(coordinator))
    if coordinator.offers(FEATURE_SLEEP_TIMER, "getSleepTimer", "sleep_timer"):
        entities.append(SleepTimerNumber(coordinator))
    preset = find_custom_eq(coordinator.data.answers.get("getEQList"))
    if coordinator.has_feature(FEATURE_EQUALIZER) and preset:
        frequencies = (preset.get("eq_payload") or {}).get("fs") or []
        entities.extend(EqBandNumber(coordinator, index, float(fs)) for index, fs in enumerate(frequencies))
    async_add_entities(entities)


class AudioSyncNumber(EnchantEntity, NumberEntity):
    """Delay of the sound to match the picture."""

    _attr_translation_key = "audio_sync"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MILLISECONDS
    _attr_native_min_value = 0
    _attr_native_max_value = AUDIO_SYNC_MAX_MS
    _attr_native_step = 10
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "audio_sync")

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.data.value("getAudioSync", "audio_sync")
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        text = str(int(value))
        await self.coordinator.async_write("setAudioSync", {"audio_sync": text})
        self.coordinator.async_set_local("getAudioSync", audio_sync=text)


class SleepTimerNumber(EnchantEntity, NumberEntity):
    """Switch the speaker to standby after this many minutes; 0 turns it off."""

    _attr_translation_key = "sleep_timer"
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = SLEEP_TIMER_MAX_MIN
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "sleep_timer")

    @property
    def native_value(self) -> float | None:
        value = self.coordinator.data.value("getSleepTimer", "sleep_timer")
        try:
            return round(int(value) / 60)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        seconds = int(value) * 60
        await self.coordinator.async_write("setSleepTimer", {"sleep_timer": seconds})
        self.coordinator.async_set_local("getSleepTimer", sleep_timer=str(seconds))


class EqBandNumber(EnchantEntity, NumberEntity):
    """Gain of one band of the speaker's CUSTOMIZE equalizer preset."""

    _attr_translation_key = "eq_band"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.SOUND_PRESSURE
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_native_min_value = EQ_GAIN_MIN
    _attr_native_max_value = EQ_GAIN_MAX
    _attr_native_step = EQ_GAIN_STEP
    _attr_mode = NumberMode.SLIDER
    _unrecorded_attributes = frozenset({"frequency"})

    def __init__(self, coordinator: EnchantCoordinator, index: int, frequency: float) -> None:
        super().__init__(coordinator, f"eq_custom_{index}")
        self._index = index
        self._attr_translation_placeholders = {"band": format_frequency(frequency)}
        # Centre frequency in Hz, so that the dashboard card can order the bands.
        self._attr_extra_state_attributes = {"frequency": int(frequency) if frequency.is_integer() else frequency}

    def _preset(self) -> dict[str, Any] | None:
        return find_custom_eq(self.coordinator.data.answers.get("getEQList"))

    @property
    def native_value(self) -> float | None:
        gains = ((self._preset() or {}).get("eq_payload") or {}).get("gain") or []
        return float(gains[self._index]) if self._index < len(gains) else None

    async def async_set_native_value(self, value: float) -> None:
        preset = self._preset()
        if preset is None:
            raise HomeAssistantError("The equalizer settings are not known yet")
        try:
            payload = build_eq_band_payload(preset, self._index, value)
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err
        await self.coordinator.async_write("setActiveEQ", payload)
        answer = copy.deepcopy(self.coordinator.data.answers.get("getEQList") or {})
        for item in answer.get("eq_list") or []:
            if isinstance(item, dict) and str(item.get("eq_id")) == payload["active_eq_id"]:
                item["eq_payload"] = payload["eq_payload"]
        self.coordinator.async_set_local(
            "getEQList", eq_list=answer.get("eq_list") or [], active_eq_id=payload["active_eq_id"]
        )
