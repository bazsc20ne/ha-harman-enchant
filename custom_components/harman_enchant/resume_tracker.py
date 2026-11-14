# SPDX-License-Identifier: AGPL-3.0-only
"""When to start a player again after the speaker's AirPlay service restarts.

The speaker can withdraw its AirPlay service from the network (an mDNS goodbye) and announce
it again a second or two later. An AirPlay sender such as Music Assistant then treats the
speaker as gone and stops its stream. This module only decides; it imports nothing from
Home Assistant, so it can be tested on its own.
"""

from __future__ import annotations

from enum import StrEnum

PLAYING = "playing"
# Player states from which playback is started again.
RESUMABLE_STATES = frozenset({"idle", "paused"})


class Decision(StrEnum):
    """What to do now."""

    NOTHING = "nothing"
    WAIT = "wait"
    RESUME = "resume"
    GIVE_UP = "give_up"


class ResumeTracker:
    """Follow one restart of the AirPlay service and the player that was playing."""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout
        self._armed_at: float | None = None
        self._service_back = False

    @property
    def armed(self) -> bool:
        return self._armed_at is not None

    def service_removed(self, player_state: str | None, now: float) -> bool:
        """The service went away. Arm only if the player was playing; return whether armed."""
        if player_state == PLAYING:
            self._armed_at = now
            self._service_back = False
        return self.armed

    def service_added(self) -> None:
        """The service is announced again."""
        if self.armed:
            self._service_back = True

    def check(self, player_state: str | None, now: float) -> Decision:
        """Decide from the player's current state."""
        if self._armed_at is None:
            return Decision.NOTHING
        if now - self._armed_at > self._timeout:
            self.reset()
            return Decision.GIVE_UP
        if self._service_back and player_state in RESUMABLE_STATES:
            self.reset()
            return Decision.RESUME
        return Decision.WAIT

    def reset(self) -> None:
        self._armed_at = None
        self._service_back = False
