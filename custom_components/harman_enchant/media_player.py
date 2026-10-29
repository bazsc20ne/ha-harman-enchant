# SPDX-License-Identifier: AGPL-3.0-only
"""Media player of the Harman Kardon Enchant integration."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SOURCE_WRITE_VALUES, EnchantError
from .const import FEATURE_INPUTS
from .coordinator import EnchantConfigEntry, EnchantCoordinator
from .entity import EnchantEntity

PARALLEL_UPDATES = 1

_PLAYBACK_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
)

# UPnP AVTransport states while a streaming service plays.
_TRANSPORT_STATES = {
    "PLAYING": MediaPlayerState.PLAYING,
    "PAUSED_PLAYBACK": MediaPlayerState.PAUSED,
    "TRANSITIONING": MediaPlayerState.BUFFERING,
    "STOPPED": MediaPlayerState.IDLE,
    "NO_MEDIA_PRESENT": MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EnchantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the media player."""
    async_add_entities([EnchantMediaPlayer(entry.runtime_data)])


class EnchantMediaPlayer(EnchantEntity, MediaPlayerEntity):
    """Power, volume and input of the speaker."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_volume_step = 0.01

    def __init__(self, coordinator: EnchantCoordinator) -> None:
        super().__init__(coordinator, "media_player")
        features = (
            MediaPlayerEntityFeature.TURN_ON
            | MediaPlayerEntityFeature.TURN_OFF
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )
        if coordinator.has_feature(FEATURE_INPUTS) and coordinator.supports("getMediaSourceStatus"):
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
            self._attr_source_list = list(SOURCE_WRITE_VALUES)
        self._base_features = features

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        data = self.coordinator.data
        if data.is_on and data.network_source:
            return self._base_features | _PLAYBACK_FEATURES
        return self._base_features

    @property
    def state(self) -> MediaPlayerState | None:
        data = self.coordinator.data
        if data.is_on is None:
            return None
        if not data.is_on:
            return MediaPlayerState.OFF
        if data.network_source:
            return _TRANSPORT_STATES.get(str(data.transport.get("state") or "").upper(), MediaPlayerState.ON)
        status = (data.media_status or "").lower()
        if status == "playing":
            return MediaPlayerState.PLAYING
        if status == "paused":
            return MediaPlayerState.PAUSED
        return MediaPlayerState.ON

    @property
    def source(self) -> str | None:
        return self.coordinator.data.source

    def _track(self, key: str) -> Any:
        data = self.coordinator.data
        return data.transport.get(key) if data.network_source else None

    @property
    def media_content_type(self) -> MediaType | None:
        return MediaType.MUSIC if self._track("title") else None

    @property
    def media_title(self) -> str | None:
        return self._track("title")

    @property
    def media_artist(self) -> str | None:
        return self._track("artist")

    @property
    def media_album_name(self) -> str | None:
        return self._track("album")

    @property
    def media_image_url(self) -> str | None:
        return self._track("image")

    @property
    def media_image_hash(self) -> str | None:
        if not (url := self.media_image_url):
            return None
        if url.startswith("/"):
            # The AirPlay cover keeps the same address for every track: hash its content instead.
            return self.coordinator.data.cover_hash
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        url = self.media_image_url
        if url and url.startswith("/"):
            # Served by the speaker itself, behind its client certificate.
            if cover := self.coordinator.data.cover:
                return cover
            try:
                return await self.coordinator.client.fetch_image(url)
            except EnchantError:
                return None, None
        return await super().async_get_media_image()

    @property
    def media_duration(self) -> int | None:
        return self._track("duration")

    @property
    def media_position(self) -> int | None:
        return self._track("position")

    @property
    def media_position_updated_at(self) -> datetime | None:
        return self.coordinator.data.position_updated_at if self._track("position") is not None else None

    @property
    def volume_level(self) -> float | None:
        volume = self.coordinator.data.volume
        return None if volume is None else volume / 100

    @property
    def is_volume_muted(self) -> bool | None:
        return self.coordinator.data.muted

    async def async_turn_on(self) -> None:
        await self._set_power("0")

    async def async_turn_off(self) -> None:
        await self._set_power("1")

    async def _set_power(self, state: str) -> None:
        await self.coordinator.async_write("setPowerState", {"power_state": state})
        self.coordinator.async_set_local("getPowerState", power_state=state)

    async def async_select_source(self, source: str) -> None:
        if source not in SOURCE_WRITE_VALUES:
            raise ServiceValidationError(f"Unknown source: {source}")
        value = SOURCE_WRITE_VALUES[source]
        await self.coordinator.async_write("setMediaSource", {"media_source": value})
        self.coordinator.async_set_local("getMediaSourceStatus", media_source=value)

    async def async_media_play(self) -> None:
        if self.state != MediaPlayerState.PLAYING:
            await self._press("musicPlayPause")

    async def async_media_pause(self) -> None:
        if self.state == MediaPlayerState.PLAYING:
            await self._press("musicPlayPause")

    async def async_media_next_track(self) -> None:
        await self._press("next")

    async def async_media_previous_track(self) -> None:
        await self._press("prev")

    async def _press(self, key: str) -> None:
        # The same keys as the remote control; the speaker toggles play and pause with one key.
        await self.coordinator.async_write("sendAppController", {"key_pressed": key})
        self.coordinator.async_schedule_transport_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        await self._upnp(self.coordinator.client.set_volume(round(volume * 100)))
        self.coordinator.async_set_local("getPlayerStatus", vol=str(round(volume * 100)))

    async def async_mute_volume(self, mute: bool) -> None:
        await self._upnp(self.coordinator.client.set_mute(mute))
        self.coordinator.async_set_local("getPlayerStatus", mute="1" if mute else "0")

    async def _upnp(self, call: Any) -> None:
        try:
            await call
        except EnchantError as err:
            raise HomeAssistantError(str(err)) from err
