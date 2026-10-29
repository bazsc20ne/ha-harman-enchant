# SPDX-License-Identifier: AGPL-3.0-only
"""Tests of the protocol helpers (no Home Assistant needed)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys

import pytest

_API_PATH = Path(__file__).parents[1] / "custom_components" / "harman_enchant" / "api.py"
_spec = importlib.util.spec_from_file_location("harman_enchant_api", _API_PATH)
api = importlib.util.module_from_spec(_spec)
sys.modules["harman_enchant_api"] = api
_spec.loader.exec_module(api)


def test_build_command_body_without_payload() -> None:
    assert api.build_command_body("getPowerState") == "command=getPowerState"


def test_build_command_body_with_compact_payload() -> None:
    body = api.build_command_body("setMediaSource", {"media_source": "BT"})
    assert body == 'command=setMediaSource&payload={"media_source":"BT"}'


def test_parse_command_response_ok() -> None:
    result = api.parse_command_response("getPowerState", '{"error_code":"0","power_state":"1"}')
    assert result["power_state"] == "1"


def test_parse_command_response_without_error_code() -> None:
    result = api.parse_command_response("getPlayerStatus", '{"vol":"15","mute":"0"}')
    assert result["vol"] == "15"


def test_parse_command_response_unknown_command() -> None:
    with pytest.raises(api.EnchantUnsupportedCommand):
        api.parse_command_response("getNightMode", "unknown command")


def test_parse_command_response_error_code() -> None:
    with pytest.raises(api.EnchantCommandError):
        api.parse_command_response("setAudioSync", '{"error_code":"1"}')


def test_parse_command_response_not_json() -> None:
    with pytest.raises(api.EnchantConnectionError):
        api.parse_command_response("getPowerState", "<html>")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TV", "TV"),
        ("HDMI1", "HDMI"),
        ("HDMI", "HDMI"),
        ("BT", "Bluetooth"),
        ("BLUETOOTH", "Bluetooth"),
        ("AP2", "AirPlay"),
        ("IDLE", "IDLE"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_source(raw: str | None, expected: str | None) -> None:
    assert api.normalize_source(raw) == expected


def test_source_write_values() -> None:
    assert api.SOURCE_WRITE_VALUES == {"TV": "TV", "HDMI": "HDMI", "Bluetooth": "BT"}


def test_format_stream_info_full() -> None:
    info = {
        "source": "com.harman.TV",
        "codec_type": "Dolby Digital Plus",
        "proc_type": "Dolby Surround",
        "channels": 8,
        "sample_rate": 48000,
    }
    assert api.format_stream_info(info) == "Dolby Digital Plus / Dolby Surround / 8ch / 48 kHz"


def test_format_stream_info_no_signal() -> None:
    info = {"source": "com.harman.TV", "codec_type": "   ", "proc_type": "", "channels": 0, "sample_rate": 0}
    assert api.format_stream_info(info) is None


def test_format_stream_info_pcm() -> None:
    assert api.format_stream_info({"codec_type": "PCM", "channels": 2, "sample_rate": "44100"}) == (
        "PCM / 2ch / 44.1 kHz"
    )


def test_format_stream_info_same_proc_and_codec() -> None:
    assert api.format_stream_info({"proc_type": "PCM", "codec_type": "PCM"}) == "PCM"


def test_format_stream_info_empty() -> None:
    assert api.format_stream_info({}) is None


def _notify(inner: str, escape_twice: bool = False) -> str:
    import html

    escaped = html.escape(inner, quote=True)
    if escape_twice:
        escaped = html.escape(escaped, quote=True)
    return (
        "<?xml version='1.0' encoding='UTF-8' ?>"
        '<e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0"><e:property>'
        f"<LastChange>{escaped}</LastChange></e:property></e:propertyset>"
    )


def test_parse_event_rendering_control() -> None:
    inner = (
        '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/"><InstanceID val="0">'
        '<Mute channel="Master" val="0"/><Volume channel="Master" val="15"/>'
        "</InstanceID></Event>"
    )
    assert api.parse_event(_notify(inner)) == {"Mute": "0", "Volume": "15"}


@pytest.mark.parametrize("twice", [False, True])
def test_parse_event_harman_state(twice: bool) -> None:
    state = {"tv_stream_info": {"codec_type": "PCM", "channels": 2, "sample_rate": 48000}}
    inner = (
        '<Event xmlns="urn:schemas-upnp-org:metadata-1-0/RCS/"><InstanceID val="0">'
        f'<HarmanBarState val="{json.dumps(state).replace(chr(34), "&quot;")}"/>'
        "</InstanceID></Event>"
    )
    values = api.parse_event(_notify(inner, escape_twice=twice))
    assert values["HarmanBarState"] == state


def test_parse_event_garbage() -> None:
    assert api.parse_event("not xml") == {}


def test_parse_group_info() -> None:
    answer = {
        "error_code": "0",
        "group_info": {
            "disabled": False,
            "group": {"multichannelType": "5.1.4", "type": "multichannel"},
            "members": [
                {"device_name": "Harman Kardon Enchant 900", "friendly_name": "Bar", "channel": ["front_left"]},
                {"device_name": "Harman Kardon Enchant Sub", "friendly_name": "Sub", "channel": ["low_frequency"]},
            ],
        },
    }
    group = api.parse_group_info(answer)
    assert group is not None
    assert group.layout == "5.1.4"
    assert [m.device_name for m in group.members] == [
        "Harman Kardon Enchant 900",
        "Harman Kardon Enchant Sub",
    ]
    assert group.members[1].channels == ["low_frequency"]


def test_parse_group_info_disabled() -> None:
    assert api.parse_group_info({"group_info": {"disabled": True}}) is None
    assert api.parse_group_info({"error_code": "0"}) is None


def test_parse_soap_fields() -> None:
    text = "<r><CurrentVolume>15</CurrentVolume><PlayMedium>TV</PlayMedium></r>"
    assert api.parse_soap_fields(text, ("CurrentVolume", "PlayMedium", "Missing")) == {
        "CurrentVolume": "15",
        "PlayMedium": "TV",
        "Missing": None,
    }


def test_bundled_certificate_loads() -> None:
    context = api.create_ssl_context()
    assert context.verify_mode.name == "CERT_NONE"


_EQ_LIST = {
    "active_eq_id": "1",
    "eq_list": [
        {"band": 7, "eq_id": "1", "eq_name": "JBL SIGNATURE", "eq_payload": {"fs": [125, 250], "gain": [0, 0]}},
        {"band": 7, "eq_id": "0", "eq_name": "CUSTOMIZE", "eq_payload": {"fs": [125, 250], "gain": [2.5, 0.5]}},
    ],
}


def test_find_custom_eq() -> None:
    preset = api.find_custom_eq(_EQ_LIST)
    assert preset is not None
    assert preset["eq_id"] == "0"


def test_find_custom_eq_missing() -> None:
    assert api.find_custom_eq({"eq_list": [{"eq_name": "VOCAL"}]}) is None
    assert api.find_custom_eq(None) is None
    assert api.find_custom_eq({"eq_list": "x"}) is None


def test_build_eq_band_payload_selects_preset_and_keeps_original() -> None:
    preset = api.find_custom_eq(_EQ_LIST)
    payload = api.build_eq_band_payload(preset, 1, -6.0)
    assert payload == {"active_eq_id": "0", "band": 7, "eq_payload": {"fs": [125, 250], "gain": [2.5, -6]}}
    assert preset["eq_payload"]["gain"] == [2.5, 0.5]


def test_build_eq_band_payload_half_step() -> None:
    payload = api.build_eq_band_payload(api.find_custom_eq(_EQ_LIST), 0, 3.5)
    assert payload["eq_payload"]["gain"] == [3.5, 0.5]


def test_build_eq_band_payload_bad_index() -> None:
    with pytest.raises(ValueError):
        api.build_eq_band_payload(api.find_custom_eq(_EQ_LIST), 7, 1)


@pytest.mark.parametrize(("raw", "option"), [("1", "low"), ("2", "medium"), (3, "high"), ("9", None), (None, None)])
def test_atmos_option(raw: object, option: str | None) -> None:
    assert api.atmos_option(raw) == option


@pytest.mark.parametrize(("hertz", "label"), [(125, "125 Hz"), (1000, "1 kHz"), (2000.0, "2 kHz"), (8000, "8 kHz")])
def test_format_frequency(hertz: float, label: str) -> None:
    assert api.format_frequency(hertz) == label


@pytest.mark.parametrize(
    ("raw", "shown"),
    [("JBL SIGNATURE", "Signature Sound"), ("VOCAL", "Vocal"), ("ENERGETIC", "Energetic"), ("CUSTOMIZE", "Custom")],
)
def test_preset_display_name(raw: str, shown: str) -> None:
    assert api.preset_display_name(raw) == shown


class _FakeResponse:
    status = 200

    def __init__(self, text: str) -> None:
        self._text = text

    async def text(self, errors: str = "strict") -> str:
        return self._text

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeSession:
    """Fails the first `failures` posts with a closed connection, then answers."""

    def __init__(self, failures: int, text: str = '{"error_code":"0","power_state":"0"}') -> None:
        self.failures = failures
        self.calls = 0
        self.text = text

    def post(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls += 1
        if self.calls <= self.failures:
            raise api.aiohttp.ServerDisconnectedError()
        return _FakeResponse(self.text)


def _client(session: _FakeSession) -> api.EnchantClient:
    return api.EnchantClient("speaker.invalid", session, ssl_context=None)


def test_command_retries_once_after_closed_connection() -> None:
    session = _FakeSession(failures=1)
    result = asyncio.run(_client(session).command("getPowerState"))
    assert result["power_state"] == "0"
    assert session.calls == 2


def test_command_gives_up_after_second_closed_connection() -> None:
    session = _FakeSession(failures=2)
    with pytest.raises(api.EnchantConnectionError):
        asyncio.run(_client(session).command("getPowerState"))
    assert session.calls == 2


@pytest.mark.parametrize(
    ("product", "kind"),
    [
        ("Harman Kardon Enchant 1100", "soundbar"),
        ("Harman Kardon Enchant 900", "soundbar"),
        ("Harman Kardon Enchant Speaker", "speaker"),
        ("Harman Kardon Enchant Sub", "sub"),
        ("JBL Bar 1300", None),
        (None, None),
    ],
)
def test_device_kind(product: str | None, kind: str | None) -> None:
    assert api.device_kind(product) == kind


_DIDL = (
    '<DIDL-Lite xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
    "<item><dc:title>Röyksopp - What Else Is There?</dc:title><upnp:artist>unknow</upnp:artist>"
    "<upnp:album>Melody A.M.</upnp:album><upnp:albumArtURI>https://example.com/a.jpg?x=1&amp;y=2</upnp:albumArtURI>"
    "</item></DIDL-Lite>"
)


def _info_ex(state: str, medium: str, didl: str = _DIDL) -> str:
    import html

    return (
        "<s:Envelope><s:Body><u:GetInfoExResponse>"
        f"<CurrentTransportState>{state}</CurrentTransportState><TrackDuration>00:04:56</TrackDuration>"
        f"<TrackMetaData>{html.escape(didl)}</TrackMetaData><RelTime>00:02:16</RelTime>"
        f"<PlayMedium>{medium}</PlayMedium></u:GetInfoExResponse></s:Body></s:Envelope>"
    )


def test_parse_transport_info_cast() -> None:
    info = api.parse_transport_info(_info_ex("PLAYING", "CAST"))
    assert info == {
        "state": "PLAYING",
        "medium": "CAST",
        "duration": 296,
        "position": 136,
        "title": "Röyksopp - What Else Is There?",
        "artist": None,
        "album": "Melody A.M.",
        "image": "https://example.com/a.jpg?x=1&y=2",
    }


def test_parse_transport_info_no_metadata() -> None:
    info = api.parse_transport_info(_info_ex("NO_MEDIA_PRESENT", "NONE", didl=""))
    assert info["state"] == "NO_MEDIA_PRESENT"
    assert info["medium"] is None
    assert info["title"] is None


@pytest.mark.parametrize(
    ("value", "seconds"), [("00:04:56", 296), ("1:02:03", 3723), ("NOT_IMPLEMENTED", None), (None, None)]
)
def test_parse_duration(value: str | None, seconds: int | None) -> None:
    assert api.parse_duration(value) == seconds


@pytest.mark.parametrize(("raw", "name"), [("C4A", "Google Cast"), ("CAST", "Google Cast"), ("SPOTIFY", "Spotify")])
def test_network_source_names(raw: str, name: str) -> None:
    assert api.normalize_source(raw) == name
    assert name in api.NETWORK_SOURCES


@pytest.mark.parametrize(
    ("source", "key"),
    [("Google Cast", "google_cast"), ("TV", "tv"), ("IDLE", "idle"), ("MUSICSERVICE", "other"), (None, None)],
)
def test_playing_source_key(source: str | None, key: str | None) -> None:
    assert api.playing_source_key(source) == key
    if key:
        assert key in api.PLAYING_SOURCE_OPTIONS


@pytest.mark.parametrize(
    ("data", "reported", "expected"),
    [
        (b"\xff\xd8\xff\xdb\x00", "application/octet-stream", "image/jpeg"),
        (b"\x89PNG\r\n", None, "image/png"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8", None, "image/webp"),
        (b"<html>", "text/html", None),
        (b"????", "image/jpeg", "image/jpeg"),
    ],
)
def test_image_content_type(data: bytes, reported: str | None, expected: str | None) -> None:
    assert api.image_content_type(data, reported) == expected


def test_dlna_source() -> None:
    assert api.normalize_source("THIRD-DLNA") == "DLNA"
    assert "DLNA" in api.NETWORK_SOURCES
    assert api.playing_source_key("DLNA") == "dlna"
    assert api.playing_source_key("ROON") == "other"


def test_parse_group_info_layout_from_combination_id() -> None:
    answer = {
        "group_info": {
            "disabled": False,
            "group": {"combination_id": "7.1.4_20df_20e1_208d_208d", "type": "multichannel"},
            "members": [{"device_name": "Harman Kardon Enchant 1100", "channel": ["front_left"]}],
        }
    }
    group = api.parse_group_info(answer)
    assert group is not None
    assert group.layout == "7.1.4"


def test_parse_group_info_without_layout() -> None:
    group = api.parse_group_info({"group_info": {"disabled": False, "group": {"combination_id": "x"}, "members": []}})
    assert group is not None
    assert group.layout is None
