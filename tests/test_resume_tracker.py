"""Tests of the AirPlay resume decisions (no Home Assistant needed)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_PATH = Path(__file__).parents[1] / "custom_components" / "harman_enchant" / "resume_tracker.py"
_spec = importlib.util.spec_from_file_location("harman_enchant_resume_tracker", _PATH)
rt = importlib.util.module_from_spec(_spec)
sys.modules["harman_enchant_resume_tracker"] = rt
_spec.loader.exec_module(rt)

Decision = rt.Decision


def test_not_playing_does_not_arm() -> None:
    tracker = rt.ResumeTracker(60)
    assert tracker.service_removed("idle", 0) is False
    tracker.service_added()
    assert tracker.check("idle", 1) is Decision.NOTHING


def test_restart_while_playing_resumes_once() -> None:
    # As on 2026-11-14 11:44: goodbye while playing, service back after ~1.3 s, then the player stops.
    tracker = rt.ResumeTracker(60)
    assert tracker.service_removed("playing", 0) is True
    assert tracker.check("playing", 0.1) is Decision.WAIT
    tracker.service_added()
    assert tracker.check("playing", 1.3) is Decision.WAIT
    assert tracker.check("idle", 1.4) is Decision.RESUME
    assert tracker.check("idle", 1.5) is Decision.NOTHING


def test_player_stopped_before_the_service_is_back() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_removed("playing", 0)
    assert tracker.check("idle", 0.5) is Decision.WAIT
    tracker.service_added()
    assert tracker.check("idle", 1.5) is Decision.RESUME


def test_paused_player_is_resumed() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_removed("playing", 0)
    tracker.service_added()
    assert tracker.check("paused", 2) is Decision.RESUME


def test_off_or_unavailable_player_is_not_started() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_removed("playing", 0)
    tracker.service_added()
    assert tracker.check("unavailable", 2) is Decision.WAIT
    assert tracker.check("off", 3) is Decision.WAIT


def test_gives_up_after_the_timeout() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_removed("playing", 0)
    assert tracker.check("idle", 61) is Decision.GIVE_UP
    assert tracker.armed is False


def test_service_never_back_gives_up() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_removed("playing", 0)
    assert tracker.check("idle", 30) is Decision.WAIT
    assert tracker.check("idle", 61) is Decision.GIVE_UP


def test_second_goodbye_while_armed_keeps_it_armed() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_removed("playing", 0)
    assert tracker.service_removed("idle", 0.5) is True
    tracker.service_added()
    assert tracker.check("idle", 2) is Decision.RESUME


def test_service_added_without_goodbye_does_nothing() -> None:
    tracker = rt.ResumeTracker(60)
    tracker.service_added()
    assert tracker.check("idle", 1) is Decision.NOTHING
