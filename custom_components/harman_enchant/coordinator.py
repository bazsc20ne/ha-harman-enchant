# SPDX-License-Identifier: AGPL-3.0-only
"""Polling and event handling for one Enchant speaker."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import logging
from typing import Any

from aiohttp import web
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    NETWORK_SOURCES,
    SOURCE_WRITE_VALUES,
    STREAMING_MARKER,
    EnchantClient,
    EnchantCommandError,
    EnchantConnectionError,
    EnchantError,
    EnchantUnsupportedCommand,
    GroupInfo,
    device_kind,
    format_stream_info,
    normalize_source,
    parse_event,
    parse_group_info,
)
from .const import (
    DOMAIN,
    EVENT_RENEW_INTERVAL,
    EVENT_SERVICES,
    EVENT_SUBSCRIPTION_SECONDS,
    FAST_COMMANDS,
    FEATURES,
    POLL_INTERVAL,
    SETTINGS_COMMANDS,
    SETTINGS_EVERY,
)

_LOGGER = logging.getLogger(__name__)

type EnchantConfigEntry = ConfigEntry[EnchantCoordinator]

# Seconds after a track event when the track is read again; the artwork can follow the title.
_FOLLOWUP_DELAYS = (0, 0.75, 1.5, 2.5, 4, 8)


@dataclass(slots=True)
class EnchantData:
    """Everything known about the speaker."""

    answers: dict[str, dict[str, Any]] = field(default_factory=dict)
    stream_info: dict[str, Any] = field(default_factory=dict)
    transport: dict[str, Any] = field(default_factory=dict)
    position_updated_at: datetime | None = None
    # Artwork the speaker serves itself (AirPlay): bytes, content type and a hash of the content.
    cover: tuple[bytes, str | None] | None = None
    cover_hash: str | None = None

    def value(self, command: str, key: str) -> Any:
        """Return one field of a command answer, or None."""
        return self.answers.get(command, {}).get(key)

    @property
    def is_on(self) -> bool | None:
        state = self.value("getPowerState", "power_state")
        # The speaker reports "0" when on and "1" in standby.
        return None if state is None else str(state) == "0"

    @property
    def network_source(self) -> str | None:
        """The streaming service that plays (AirPlay, Google Cast, Spotify, DLNA or another one), if any."""
        streaming = self.streaming.get("source")
        medium = normalize_source(self.transport.get("medium"))
        for source in (normalize_source(streaming), medium):
            if source in NETWORK_SOURCES:
                return source
        if str(streaming or "").upper() == STREAMING_MARKER and medium not in (None, *SOURCE_WRITE_VALUES):
            # A service without a known name: show the name the speaker reports.
            return medium
        return None

    @property
    def source(self) -> str | None:
        # While a streaming service plays, getMediaSourceStatus still reports the last input.
        return self.network_source or normalize_source(self.value("getMediaSourceStatus", "media_source"))

    @property
    def playing_source(self) -> str | None:
        return self.network_source or normalize_source(self.streaming.get("source"))

    @property
    def media_status(self) -> str | None:
        return self.value("getMediaSourceStatus", "media_status")

    @property
    def volume(self) -> int | None:
        return _int(self.value("getPlayerStatus", "vol"))

    @property
    def muted(self) -> bool | None:
        mute = self.value("getPlayerStatus", "mute")
        return None if mute is None else str(mute) == "1"

    @property
    def streaming(self) -> dict[str, Any]:
        status = self.value("getStreamingStatus", "status")
        return status if isinstance(status, dict) else {}

    @property
    def is_atmos(self) -> bool | None:
        value = self.streaming.get("is_atmos")
        return None if value is None else str(value).lower() == "true"

    @property
    def audio_format(self) -> str | None:
        return format_stream_info(self.stream_info) if self.stream_info else None

    @property
    def group(self) -> GroupInfo | None:
        answer = self.answers.get("getGroupInfo")
        return parse_group_info(answer) if answer else None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class EnchantCoordinator(DataUpdateCoordinator[EnchantData]):
    """Keeps the state of one speaker up to date."""

    config_entry: EnchantConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EnchantConfigEntry,
        client: EnchantClient,
        device_info: dict[str, Any],
        status: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=POLL_INTERVAL,
        )
        self.client = client
        self.device_info = device_info
        self.status = status
        self.kind = device_kind(status.get("hm_product_name"))
        self.unsupported: set[str] = set()
        self._poll_count = 0
        self._settings_due = True
        self._data = EnchantData()
        self._sids: dict[str, str] = {}
        self._runner: web.AppRunner | None = None
        self._callback_base: str | None = None
        self._unsub_renew: CALLBACK_TYPE | None = None
        self._followups: list[CALLBACK_TYPE] = []

    def supports(self, command: str) -> bool:
        """True when the speaker answered this command."""
        return command in self._data.answers

    def has_feature(self, feature: str) -> bool:
        """True when this kind of product handles the feature."""
        return feature in FEATURES.get(self.kind or "", frozenset())

    def offers(self, feature: str, command: str, key: str) -> bool:
        """True when the product handles the feature and reported the value it is read from."""
        return self.has_feature(feature) and self._data.value(command, key) is not None

    async def _async_update_data(self) -> EnchantData:
        commands = list(FAST_COMMANDS)
        if self._settings_due or self._poll_count % SETTINGS_EVERY == 0:
            commands += SETTINGS_COMMANDS
            self._settings_due = False
        self._poll_count += 1
        failures = 0
        for command in commands:
            if command in self.unsupported:
                continue
            try:
                self._data.answers[command] = await self.client.command(command)
            except EnchantUnsupportedCommand:
                _LOGGER.debug("%s does not support %s", self.client.host, command)
                self.unsupported.add(command)
            except EnchantCommandError as err:
                _LOGGER.debug("%s", err)
            except EnchantConnectionError as err:
                failures += 1
                if command == "getPowerState":
                    raise UpdateFailed(f"{self.client.host} is not reachable: {err}") from err
        if failures:
            _LOGGER.debug("%s: %d commands failed this round", self.client.host, failures)
        await self._async_update_transport()
        return self._data

    async def _async_update_transport(self, fetch_cover: bool = False) -> None:
        """Read what a streaming service plays (title, artist, artwork, position)."""
        try:
            transport = await self.client.transport_info()
        except EnchantError as err:
            _LOGGER.debug("%s: no transport info: %s", self.client.host, err)
            return
        old = self._data.transport
        track = tuple(transport.get(key) for key in ("title", "artist", "album", "image"))
        old_track = tuple(old.get(key) for key in ("title", "artist", "album", "image"))
        now = (transport.get("position"), transport.get("state"), track)
        if now != (old.get("position"), old.get("state"), old_track):
            self._data.position_updated_at = dt_util.utcnow()
        self._data.transport = transport
        image = transport.get("image")
        if not (image and image.startswith("/")):
            self._data.cover = self._data.cover_hash = None
        elif fetch_cover or track != old_track or self._data.cover is None:
            try:
                cover = await self.client.fetch_image(image)
            except EnchantError as err:
                _LOGGER.debug("%s: no artwork: %s", self.client.host, err)
            else:
                self._data.cover = cover
                self._data.cover_hash = hashlib.sha256(cover[0]).hexdigest()[:16]

    @callback
    def async_schedule_transport_refresh(self) -> None:
        """Read the track right away and a few times more, as the artwork can follow the title."""
        for unsub in self._followups:
            unsub()
        self._followups = [
            async_call_later(self.hass, delay, self._async_transport_followup) for delay in _FOLLOWUP_DELAYS
        ]

    async def _async_transport_followup(self, _now: datetime) -> None:
        await self._async_update_transport(fetch_cover=True)
        self.async_set_updated_data(self._data)

    async def async_write(self, command: str, payload: dict[str, Any]) -> None:
        """Send a setting, then refresh soon after."""
        try:
            await self.client.command(command, payload)
        except EnchantError as err:
            raise HomeAssistantError(f"{command} failed: {err}") from err
        self._settings_due = True
        await self.async_request_refresh()

    @callback
    def async_set_local(self, command: str, **values: Any) -> None:
        """Update a cached answer right away so the UI follows the change."""
        self._data.answers.setdefault(command, {}).update(values)
        self.async_set_updated_data(self._data)

    # Events -------------------------------------------------------------

    async def async_start_events(self, source_ip: str) -> None:
        """Listen for UPnP event notifications and subscribe to them."""
        app = web.Application()
        app.router.add_route("NOTIFY", "/{service}", self._handle_notify)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, host=source_ip, port=0)
        await site.start()
        self._runner = runner
        port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
        self._callback_base = f"http://{source_ip}:{port}"
        await self._async_renew_subscriptions()
        self._unsub_renew = async_track_time_interval(self.hass, self._async_renew_subscriptions, EVENT_RENEW_INTERVAL)

    async def _async_renew_subscriptions(self, *_: Any) -> None:
        for service in EVENT_SERVICES:
            try:
                sid, _granted = await self.client.subscribe(
                    service,
                    f"{self._callback_base}/{service}",
                    self._sids.get(service),
                    EVENT_SUBSCRIPTION_SECONDS,
                )
            except EnchantError:
                # The subscription may have expired (e.g. after a speaker restart).
                self._sids.pop(service, None)
                try:
                    sid, _granted = await self.client.subscribe(
                        service,
                        f"{self._callback_base}/{service}",
                        None,
                        EVENT_SUBSCRIPTION_SECONDS,
                    )
                except EnchantError as err:
                    _LOGGER.debug("Event subscription %s failed: %s", service, err)
                    continue
            self._sids[service] = sid

    async def _handle_notify(self, request: web.Request) -> web.Response:
        if request.remote != self.client.host:
            return web.Response(status=403)
        body = await request.text()
        values = parse_event(body)
        state = values.get("HarmanBarState")
        if isinstance(state, dict):
            info = state.get("tv_stream_info")
            if isinstance(info, dict):
                self._data.stream_info = info
                self.async_set_updated_data(self._data)
        player = {}
        if "Volume" in values:
            player["vol"] = str(values["Volume"])
        if "Mute" in values:
            player["mute"] = str(values["Mute"])
        if player:
            self.async_set_local("getPlayerStatus", **player)
        if any(key in values for key in ("TransportState", "CurrentTrackMetaData", "AVTransportURI")):
            self.async_schedule_transport_refresh()
        if any(key in values for key in ("TransportState", "PlaybackStorageMedium")):
            self.hass.async_create_task(self.async_request_refresh())
        return web.Response()

    async def async_shutdown(self) -> None:
        """Stop events and polling."""
        for unsub in self._followups:
            unsub()
        self._followups = []
        if self._unsub_renew:
            self._unsub_renew()
            self._unsub_renew = None
        for service, sid in list(self._sids.items()):
            await self.client.unsubscribe(service, sid)
        self._sids.clear()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        await super().async_shutdown()
