# SPDX-License-Identifier: AGPL-3.0-only
"""Select entities of the Harman Kardon Enchant integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ATMOS_LEVELS, atmos_option, preset_display_name
from .const import FEATURE_ATMOS_LEVEL, FEATURE_EQUALIZER
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the select entities the speaker supports."""
    coordinator = entry.runtime_data
    entities: list[SelectEntity] = []
    if coordinator.has_feature(FEATURE_EQUALIZER) and coordinator.supports("getEQList"):
        entities.append(EqPresetSelect(coordinator))
    if coordinator.offers(FEATURE_ATMOS_LEVEL, "getAtmosConfig", "atmos_level"):
        entities.append(AtmosLevelSelect(coordinator))
    async_add_entities(entities)


class EqPresetSelect(EnchantEntity, SelectEntity):
    """The active equalizer preset."""

    _attr_translation_key = "eq_preset"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "eq_preset")

    def _presets(self) -> list[dict[str, Any]]:
        presets = self.coordinator.data.value("getEQList", "eq_list")
        return [p for p in presets or [] if isinstance(p, dict) and p.get("eq_name")]

    @property
    def options(self) -> list[str]:
        return [preset_display_name(p["eq_name"]) for p in self._presets()]

    @property
    def current_option(self) -> str | None:
        active = self.coordinator.data.value("getEQList", "active_eq_id")
        for preset in self._presets():
            if str(preset.get("eq_id")) == str(active):
                return preset_display_name(preset["eq_name"])
        return None

    async def async_select_option(self, option: str) -> None:
        for preset in self._presets():
            if preset_display_name(preset["eq_name"]) == option:
                break
        else:
            raise ServiceValidationError(f"Unknown equalizer preset: {option}")
        eq_id = str(preset.get("eq_id"))
        await self.coordinator.async_write(
            "setActiveEQ",
            {
                "active_eq_id": eq_id,
                "band": preset.get("band", len((preset.get("eq_payload") or {}).get("gain") or [])),
                "eq_payload": preset.get("eq_payload") or {},
            },
        )
        self.coordinator.async_set_local("getEQList", active_eq_id=eq_id)


class AtmosLevelSelect(EnchantEntity, SelectEntity):
    """Strength of the height (Dolby Atmos) effect."""

    _attr_translation_key = "atmos_level"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(ATMOS_LEVELS)

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "atmos_level")

    @property
    def current_option(self) -> str | None:
        return atmos_option(self.coordinator.data.value("getAtmosConfig", "atmos_level"))

    async def async_select_option(self, option: str) -> None:
        if option not in ATMOS_LEVELS:
            raise ServiceValidationError(f"Unknown level: {option}")
        level = ATMOS_LEVELS[option]
        status = self.coordinator.data.value("getAtmosConfig", "status") or "on"
        await self.coordinator.async_write("setAtmosConfig", {"atmos_level": level, "status": status})
        self.coordinator.async_set_local("getAtmosConfig", atmos_level=level)
