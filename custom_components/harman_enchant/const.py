# SPDX-License-Identifier: AGPL-3.0-only
"""Constants of the Harman Kardon Enchant integration."""

from datetime import timedelta

from .api import KIND_SOUNDBAR, KIND_SPEAKER

DOMAIN = "harman_enchant"
MANUFACTURER = "Harman Kardon"

POLL_INTERVAL = timedelta(seconds=10)
# Settings change rarely; they are read every SETTINGS_EVERY polls and after writes.
SETTINGS_EVERY = 6

EVENT_SUBSCRIPTION_SECONDS = 300
EVENT_RENEW_INTERVAL = timedelta(seconds=240)
EVENT_SERVICES = ("rendercontrol1", "rendertransport1")

# Commands polled on every update.
FAST_COMMANDS = (
    "getPowerState",
    "getMediaSourceStatus",
    "getPlayerStatus",
    "getStreamingStatus",
)

# Commands polled every SETTINGS_EVERY updates.
SETTINGS_COMMANDS = (
    "getPersonalListeningMode",
    "getSmartMode",
    "getPureVoiceState",
    "getFeedbackToneConfig",
    "getAudioSync",
    "getAtmosConfig",
    "getSleepTimer",
    "getEQList",
    "getGroupInfo",
)

AUDIO_SYNC_MAX_MS = 250

# The speaker stores any value; these limits follow the vendor app.
EQ_GAIN_MIN = -6.0
EQ_GAIN_MAX = 6.0
EQ_GAIN_STEP = 0.5
SLEEP_TIMER_MAX_MIN = 120

# What each kind of product handles: from the vendor documentation, the vendor app and tests.
FEATURE_INPUTS = "inputs"
FEATURE_EQUALIZER = "equalizer"
FEATURE_ATMOS_LEVEL = "atmos_level"
FEATURE_SMART_MODE = "smart_mode"
FEATURE_LISTEN_MODE = "listen_mode"
FEATURE_PURE_VOICE = "pure_voice"
FEATURE_FEEDBACK_TONES = "feedback_tones"
FEATURE_AUDIO_SYNC = "audio_sync"
FEATURE_SLEEP_TIMER = "sleep_timer"
FEATURE_TV_AUDIO = "tv_audio"
FEATURE_CALIBRATE = "calibrate"
FEATURE_SURROUND_LAYOUT = "surround_layout"
FEATURE_MOMENT = "moment"

FEATURES: dict[str, frozenset[str]] = {
    KIND_SOUNDBAR: frozenset(
        {
            FEATURE_INPUTS,
            FEATURE_EQUALIZER,
            FEATURE_ATMOS_LEVEL,
            FEATURE_SMART_MODE,
            FEATURE_LISTEN_MODE,
            FEATURE_PURE_VOICE,
            FEATURE_FEEDBACK_TONES,
            FEATURE_AUDIO_SYNC,
            FEATURE_SLEEP_TIMER,
            FEATURE_TV_AUDIO,
            FEATURE_CALIBRATE,
            FEATURE_SURROUND_LAYOUT,
        }
    ),
    KIND_SPEAKER: frozenset({FEATURE_EQUALIZER, FEATURE_SLEEP_TIMER, FEATURE_MOMENT}),
}
