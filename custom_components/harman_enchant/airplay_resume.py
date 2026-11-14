# SPDX-License-Identifier: AGPL-3.0-only
"""Start a player again after the speaker's AirPlay service restarts (option)."""

from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components import zeroconf
from homeassistant.const import ATTR_ENTITY_ID, SERVICE_MEDIA_PLAY
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from zeroconf import ServiceStateChange, Zeroconf
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

from .api import resolve_addresses
from .const import AIRPLAY_SERVICE, RESUME_SETTLE_SECONDS, RESUME_TIMEOUT_SECONDS
from .coordinator import EnchantConfigEntry
from .resume_tracker import RESUMABLE_STATES, Decision, ResumeTracker

_LOGGER = logging.getLogger(__name__)


class AirPlayResume:
    """Watch the speaker's AirPlay service and start the chosen player again after a restart."""

    def __init__(self, hass: HomeAssistant, entry: EnchantConfigEntry, host: str, player: str) -> None:
        self._hass = hass
        self._entry = entry
        self._host = host
        self._player = player
        self._tracker = ResumeTracker(RESUME_TIMEOUT_SECONDS)
        self._addresses: set[str] = set()
        # AirPlay service names announced from the speaker's addresses.
        self._names: set[str] = set()
        self._zc: Zeroconf | None = None
        self._browser: AsyncServiceBrowser | None = None
        self._unsub_player: CALLBACK_TYPE | None = None
        self._cancel_timeout: CALLBACK_TYPE | None = None
        self._cancel_resume: CALLBACK_TYPE | None = None

    async def async_start(self) -> None:
        try:
            self._addresses = await resolve_addresses(self._host)
        except OSError as err:
            _LOGGER.warning("AirPlay resume is off: %s could not be resolved: %s", self._host, err)
            return
        self._zc = (await zeroconf.async_get_async_instance(self._hass)).zeroconf
        self._browser = AsyncServiceBrowser(self._zc, AIRPLAY_SERVICE, handlers=[self._on_service_state_change])
        self._unsub_player = async_track_state_change_event(self._hass, [self._player], self._on_player_state)
        _LOGGER.debug("AirPlay resume watches %s for %s", self._host, self._player)

    async def async_stop(self) -> None:
        for cancel in (self._unsub_player, self._cancel_timeout, self._cancel_resume):
            if cancel:
                cancel()
        self._unsub_player = self._cancel_timeout = self._cancel_resume = None
        if self._browser:
            await self._browser.async_cancel()
            self._browser = None

    def _on_service_state_change(
        self, zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange
    ) -> None:
        # zeroconf passes these by keyword; hand over to the event loop.
        self._hass.loop.call_soon_threadsafe(self._handle_service_change, name, state_change)

    @callback
    def _handle_service_change(self, name: str, state_change: ServiceStateChange) -> None:
        if state_change is ServiceStateChange.Removed:
            if name not in self._names:
                return
            if self._tracker.service_removed(self._player_state(), time.monotonic()):
                _LOGGER.info("AirPlay service of %s went away while %s was playing", self._host, self._player)
                if self._cancel_timeout:
                    self._cancel_timeout()
                self._cancel_timeout = async_call_later(self._hass, RESUME_TIMEOUT_SECONDS + 1, self._async_check_timer)
            else:
                _LOGGER.debug("AirPlay service of %s went away; %s was not playing", self._host, self._player)
            return
        if name in self._names:
            if self._tracker.armed:
                _LOGGER.debug("AirPlay service of %s is back", self._host)
                self._tracker.service_added()
                self._check()
            return
        self._entry.async_create_background_task(
            self._hass, self._async_learn_name(name), f"harman_enchant AirPlay service {name}"
        )

    async def _async_learn_name(self, name: str) -> None:
        """Remember the service if it is announced from the speaker's addresses."""
        if self._zc is None:
            return
        info = AsyncServiceInfo(AIRPLAY_SERVICE, name)
        if not await info.async_request(self._zc, 3000):
            return
        if self._addresses & set(info.parsed_addresses()):
            self._names.add(name)
            _LOGGER.debug("AirPlay service of %s: %s", self._host, name)

    @callback
    def _on_player_state(self, event: Event[EventStateChangedData]) -> None:
        self._check()

    @callback
    def _async_check_timer(self, _now: Any) -> None:
        self._cancel_timeout = None
        self._check()

    @callback
    def _check(self) -> None:
        decision = self._tracker.check(self._player_state(), time.monotonic())
        if decision is Decision.RESUME:
            # Give the sender a moment to set the player up again.
            self._cancel_resume = async_call_later(self._hass, RESUME_SETTLE_SECONDS, self._async_resume)
        elif decision is Decision.GIVE_UP:
            _LOGGER.info(
                "Not resuming %s: it did not stop, or the AirPlay service of %s did not come back within %s s",
                self._player,
                self._host,
                RESUME_TIMEOUT_SECONDS,
            )

    async def _async_resume(self, _now: Any) -> None:
        self._cancel_resume = None
        if self._cancel_timeout:
            self._cancel_timeout()
            self._cancel_timeout = None
        state = self._player_state()
        if state not in RESUMABLE_STATES:
            _LOGGER.info("Not resuming %s: it is %s now", self._player, state)
            return
        try:
            await self._hass.services.async_call(
                "media_player", SERVICE_MEDIA_PLAY, {ATTR_ENTITY_ID: self._player}, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Resuming %s failed: %s", self._player, err)
            return
        _LOGGER.info("Resumed %s after the AirPlay service of %s restarted", self._player, self._host)

    def _player_state(self) -> str | None:
        state = self._hass.states.get(self._player)
        return state.state if state else None
