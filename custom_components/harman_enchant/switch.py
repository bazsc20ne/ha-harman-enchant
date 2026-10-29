# SPDX-License-Identifier: AGPL-3.0-only
"""Switches of the Harman Kardon Enchant integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    FEATURE_FEEDBACK_TONES,
    FEATURE_LISTEN_MODE,
    FEATURE_PURE_VOICE,
    FEATURE_SMART_MODE,
)
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class EnchantSwitchDescription(SwitchEntityDescription):
    """A setting that is either on or off."""

    feature: str
    read: str
    write: str
    field: str
    on_value: str
    off_value: str


SWITCHES = (
    EnchantSwitchDescription(
        key="listen_mode",
        translation_key="listen_mode",
        feature=FEATURE_LISTEN_MODE,
        entity_category=EntityCategory.CONFIG,
        read="getPersonalListeningMode",
        write="setPersonalListeningMode",
        field="status",
        on_value="on",
        off_value="off",
    ),
    EnchantSwitchDescription(
        key="smart_mode",
        translation_key="smart_mode",
        feature=FEATURE_SMART_MODE,
        entity_category=EntityCategory.CONFIG,
        read="getSmartMode",
        write="setSmartMode",
        field="status",
        on_value="on",
        off_value="off",
    ),
    EnchantSwitchDescription(
        key="pure_voice",
        translation_key="pure_voice",
        feature=FEATURE_PURE_VOICE,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        read="getPureVoiceState",
        write="setPureVoiceState",
        field="purevoice_state",
        on_value="1",
        off_value="0",
    ),
    EnchantSwitchDescription(
        key="feedback_tones",
        translation_key="feedback_tones",
        feature=FEATURE_FEEDBACK_TONES,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        read="getFeedbackToneConfig",
        write="setFeedbackToneConfig",
        field="status",
        on_value="on",
        off_value="off",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the switches the speaker supports."""
    coordinator = entry.runtime_data
    async_add_entities(
        EnchantSwitch(coordinator, description)
        for description in SWITCHES
        if coordinator.offers(description.feature, description.read, description.field)
    )


class EnchantSwitch(EnchantEntity, SwitchEntity):
    """An on/off setting of the speaker."""

    entity_description: EnchantSwitchDescription

    def __init__(self, coordinator: EnchantCoordinator, description: EnchantSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.value(self.entity_description.read, self.entity_description.field)
        return None if value is None else str(value) == self.entity_description.on_value

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(self.entity_description.on_value)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(self.entity_description.off_value)

    async def _set(self, value: str) -> None:
        description = self.entity_description
        await self.coordinator.async_write(description.write, {description.field: value})
        self.coordinator.async_set_local(description.read, **{description.field: value})
