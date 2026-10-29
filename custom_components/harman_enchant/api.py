# SPDX-License-Identifier: AGPL-3.0-only
"""Local API client for Harman Kardon Enchant speakers.

The speakers expose two local interfaces:

* ``https://<host>/httpapi.asp`` - a form-encoded command API protected by a TLS
  client certificate. Every request is ``command=<name>`` with an optional
  ``&payload=<compact JSON>``; answers are JSON with ``error_code`` "0" on success,
  or the plain text ``unknown command``.
* UPnP on port 59152 (control) and 49152 (eventing) - volume, mute and event
  notifications.

This module has no Home Assistant dependency so it can be tested on its own.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
import html
import json
from pathlib import Path
import re
import socket
import ssl
from typing import Any
from xml.etree import ElementTree as ET

import aiohttp

UPNP_CONTROL_PORT = 59152
UPNP_EVENT_PORT = 49152
REQUEST_TIMEOUT = 8
MAX_PARALLEL_REQUESTS = 3

CERT_DIR = Path(__file__).parent / "certs"

SOURCE_TV = "TV"
SOURCE_HDMI = "HDMI"
SOURCE_BLUETOOTH = "Bluetooth"
SOURCE_AIRPLAY = "AirPlay"
SOURCE_CAST = "Google Cast"
SOURCE_SPOTIFY = "Spotify"
SOURCE_DLNA = "DLNA"

# getStreamingStatus reports this for any streaming service; PlayMedium then tells which one.
STREAMING_MARKER = "MUSICSERVICE"

# Streaming sources that report what they play over UPnP.
NETWORK_SOURCES = frozenset({SOURCE_AIRPLAY, SOURCE_CAST, SOURCE_SPOTIFY, SOURCE_DLNA})

# Display name -> value accepted by setMediaSource.
SOURCE_WRITE_VALUES = {SOURCE_TV: "TV", SOURCE_HDMI: "HDMI", SOURCE_BLUETOOTH: "BT"}

# Values seen in getMediaSourceStatus / getStreamingStatus / UPnP PlayMedium.
_SOURCE_READ_VALUES = {
    "TV": SOURCE_TV,
    "HDMI": SOURCE_HDMI,
    "HDMI1": SOURCE_HDMI,
    "HDMI2": SOURCE_HDMI,
    "BT": SOURCE_BLUETOOTH,
    "BLUETOOTH": SOURCE_BLUETOOTH,
    "AP2": SOURCE_AIRPLAY,
    "AIRPLAY": SOURCE_AIRPLAY,
    "C4A": SOURCE_CAST,
    "CAST": SOURCE_CAST,
    "SPOTIFY": SOURCE_SPOTIFY,
    "THIRD-DLNA": SOURCE_DLNA,
}

# Kinds of Enchant products.
KIND_SOUNDBAR = "soundbar"
KIND_SPEAKER = "speaker"
KIND_SUB = "sub"

# Name of the equalizer preset the user can edit in the vendor app.
CUSTOM_EQ_NAME = "CUSTOMIZE"

# Display names of equalizer presets that differ from the plain title case of the speaker's name.
_PRESET_NAMES = {"JBL SIGNATURE": "Signature Sound", "CUSTOMIZE": "Custom"}

# Height (Dolby Atmos) effect level: option -> value of setAtmosConfig "atmos_level".
ATMOS_LEVELS = {"low": "1", "medium": "2", "high": "3"}

_SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
    '<u:{action} xmlns:u="urn:schemas-upnp-org:service:{service}:1">'
    "<InstanceID>0</InstanceID>{args}</u:{action}></s:Body></s:Envelope>"
)

_SOAP_PATHS = {
    "RenderingControl": "rendercontrol1",
    "AVTransport": "rendertransport1",
}


# The speaker closes idle kept-alive connections; a request that hits one is sent again once.
_STALE_CONNECTION_ERRORS = (aiohttp.ServerDisconnectedError, aiohttp.ClientOSError)


class EnchantError(Exception):
    """Base error of the Enchant client."""


class EnchantConnectionError(EnchantError):
    """The speaker could not be reached or answered with garbage."""


class EnchantCommandError(EnchantError):
    """The speaker rejected a command (error_code other than "0")."""


class EnchantUnsupportedCommand(EnchantError):
    """The speaker does not know this command."""


class EnchantCertificateError(EnchantError):
    """The speaker presented another certificate than the one recorded at setup."""


def create_ssl_context(server_certificate: str | None = None, cert_dir: Path = CERT_DIR) -> ssl.SSLContext:
    """Build the TLS context with the client certificate.

    This reads files from disk, so call it from an executor.
    The speakers use self-signed server certificates. With ``server_certificate``
    (PEM) only that certificate is accepted; without it the server certificate is
    not checked, which is only used to read it at setup.
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    if server_certificate:
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cadata=server_certificate)
    else:
        context.verify_mode = ssl.CERT_NONE
    context.load_cert_chain(cert_dir / "cert.pem", cert_dir / "key.pem")
    return context


async def fetch_server_certificate(host: str, ssl_context: ssl.SSLContext, port: int = 443) -> str:
    """Return the server certificate of the speaker (PEM), read without checking it."""
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            _reader, writer = await asyncio.open_connection(host, port, ssl=ssl_context)
    except (TimeoutError, OSError) as err:
        raise EnchantConnectionError(f"{host}: {err!r}") from err
    try:
        ssl_object = writer.get_extra_info("ssl_object")
        certificate = ssl_object.getpeercert(binary_form=True) if ssl_object else None
    finally:
        writer.close()
    if not certificate:
        raise EnchantConnectionError(f"{host}: no server certificate")
    return ssl.DER_cert_to_PEM_cert(certificate)


async def resolve_addresses(host: str) -> set[str]:
    """IP addresses of a host name; an IP address gives itself."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return {str(info[4][0]) for info in infos}


def build_command_body(name: str, payload: dict[str, Any] | None = None) -> str:
    """Build the form body of an httpapi request."""
    body = f"command={name}"
    if payload is not None:
        body += "&payload=" + json.dumps(payload, separators=(",", ":"))
    return body


def parse_command_response(name: str, text: str) -> dict[str, Any]:
    """Turn an httpapi answer into a dict or raise the matching error."""
    if "unknown command" in text:
        raise EnchantUnsupportedCommand(name)
    try:
        result = json.loads(text)
    except ValueError as err:
        raise EnchantConnectionError(f"{name}: answer is not JSON") from err
    if not isinstance(result, dict):
        raise EnchantConnectionError(f"{name}: answer is not a JSON object")
    code = result.get("error_code")
    if code is not None and str(code) != "0":
        raise EnchantCommandError(f"{name}: error_code {code}")
    return result


def normalize_source(value: str | None) -> str | None:
    """Map a source value reported by the speaker to its display name."""
    if not value:
        return None
    return _SOURCE_READ_VALUES.get(value.upper(), value)


# State keys of the playing source sensor.
PLAYING_SOURCE_KEYS = {
    SOURCE_TV: "tv",
    SOURCE_HDMI: "hdmi",
    SOURCE_BLUETOOTH: "bluetooth",
    SOURCE_AIRPLAY: "airplay",
    SOURCE_CAST: "google_cast",
    SOURCE_SPOTIFY: "spotify",
    SOURCE_DLNA: "dlna",
}
PLAYING_SOURCE_OPTIONS = [*PLAYING_SOURCE_KEYS.values(), "idle", "other"]


def playing_source_key(source: str | None) -> str | None:
    """State key of the playing source sensor: tv, google_cast, idle, other, ..."""
    if not source:
        return None
    if source.upper() == "IDLE":
        return "idle"
    return PLAYING_SOURCE_KEYS.get(source, "other")


def format_stream_info(info: dict[str, Any]) -> str | None:
    """Describe an incoming audio stream, e.g. ``Dolby Digital Plus / Dolby Surround / 8ch / 48 kHz``.

    Returns None when no signal arrives (the speaker then reports a blank codec).
    """
    parts: list[str] = []
    for key in ("codec_type", "proc_type"):
        value = str(info.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    if not parts:
        return None
    try:
        channels = int(info.get("channels") or 0)
    except (TypeError, ValueError):
        channels = 0
    if channels:
        parts.append(f"{channels}ch")
    rate = info.get("sample_rate")
    try:
        rate_hz = int(rate or 0)
    except (TypeError, ValueError):
        rate_hz = 0
    if rate_hz:
        parts.append(f"{rate_hz / 1000:g} kHz")
    return " / ".join(parts) or None


def device_kind(product_name: str | None) -> str | None:
    """Kind of an Enchant product from its product name; None if it is not an Enchant."""
    name = str(product_name or "").lower()
    if "enchant" not in name:
        return None
    if "enchant sub" in name:
        return KIND_SUB
    if "enchant speaker" in name:
        return KIND_SPEAKER
    return KIND_SOUNDBAR


def find_custom_eq(answer: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return the user-editable preset of a getEQList answer, or None."""
    presets = (answer or {}).get("eq_list")
    if not isinstance(presets, list):
        return None
    for preset in presets:
        if isinstance(preset, dict) and str(preset.get("eq_name", "")).upper() == CUSTOM_EQ_NAME:
            return preset
    return None


def build_eq_band_payload(preset: dict[str, Any], index: int, gain: float) -> dict[str, Any]:
    """Return the setActiveEQ payload that changes one band of a preset and selects it."""
    eq_payload = copy.deepcopy(preset.get("eq_payload") or {})
    gains = eq_payload.get("gain")
    if not isinstance(gains, list) or not 0 <= index < len(gains):
        raise ValueError(f"The preset has no band {index}")
    gains[index] = int(gain) if float(gain).is_integer() else float(gain)
    return {
        "active_eq_id": str(preset.get("eq_id")),
        "band": preset.get("band", len(gains)),
        "eq_payload": eq_payload,
    }


def preset_display_name(eq_name: str) -> str:
    """ "JBL SIGNATURE" -> "Signature Sound", "VOCAL" -> "Vocal"."""
    name = str(eq_name).strip()
    return _PRESET_NAMES.get(name.upper(), name.title())


def atmos_option(level: Any) -> str | None:
    """Map an atmos_level value to its option name."""
    for option, value in ATMOS_LEVELS.items():
        if str(level) == value:
            return option
    return None


def format_frequency(hertz: float) -> str:
    """125 -> "125 Hz", 1000 -> "1 kHz"."""
    return f"{hertz:g} Hz" if hertz < 1000 else f"{hertz / 1000:g} kHz"


def _iter_last_change_events(body: str) -> list[ET.Element]:
    """Return the parsed ``<Event>`` documents of a GENA NOTIFY body.

    ``LastChange`` holds an escaped XML document; depending on the firmware it is
    escaped once or twice.
    """
    events: list[ET.Element] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return events
    for element in root.iter():
        if element.tag.split("}")[-1] != "LastChange" or not element.text:
            continue
        text = element.text
        for _ in range(3):
            try:
                events.append(ET.fromstring(text))
                break
            except ET.ParseError:
                unescaped = html.unescape(text)
                if unescaped == text:
                    break
                text = unescaped
    return events


def parse_event(body: str) -> dict[str, Any]:
    """Extract the values of a GENA NOTIFY body.

    Returns a flat dict of ``tag -> val`` from the event's ``InstanceID`` block.
    A ``HarmanBarState`` value (JSON) is decoded into a dict.
    """
    values: dict[str, Any] = {}
    for event in _iter_last_change_events(body):
        for element in event.iter():
            tag = element.tag.split("}")[-1]
            if tag in ("Event", "InstanceID") or "val" not in element.attrib:
                continue
            raw = element.attrib["val"]
            if tag == "HarmanBarState":
                try:
                    decoded = json.loads(html.unescape(raw))
                except ValueError:
                    continue
                if isinstance(decoded, dict):
                    values[tag] = decoded
                continue
            values[tag] = raw
    return values


def parse_soap_fields(text: str, fields: tuple[str, ...]) -> dict[str, str | None]:
    """Read simple text fields from a SOAP response."""
    result: dict[str, str | None] = {}
    for name in fields:
        match = re.search(rf"<{name}>(.*?)</{name}>", text, re.S)
        result[name] = html.unescape(match.group(1)) if match else None
    return result


_PLACEHOLDERS = {"", "unknow", "unknown", "un_known", "none", "null", "not_implemented"}
_DIDL_TAGS = {
    "title": ("dc:title",),
    "artist": ("upnp:artist", "dc:creator"),
    "album": ("upnp:album",),
    "image": ("upnp:albumArtURI",),
}


def image_content_type(data: bytes, reported: str | None = None) -> str | None:
    """Content type of an image, from its first bytes when the speaker reports a generic one."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return reported if reported and reported.startswith("image/") else None


def parse_duration(value: str | None) -> int | None:
    """ "00:04:56" -> 296; anything else -> None."""
    match = re.fullmatch(r"(\d+):(\d{1,2}):(\d{1,2})(?:\.\d+)?", (value or "").strip())
    if not match:
        return None
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = html.unescape(value).strip()
    return None if value.lower() in _PLACEHOLDERS else value


def parse_transport_info(text: str) -> dict[str, Any]:
    """Read state, medium, position and track metadata from an AVTransport GetInfoEx answer."""
    fields = parse_soap_fields(
        text, ("CurrentTransportState", "PlayMedium", "TrackDuration", "RelTime", "TrackMetaData")
    )
    info: dict[str, Any] = {
        "state": _clean(fields["CurrentTransportState"]),
        "medium": _clean(fields["PlayMedium"]),
        "duration": parse_duration(fields["TrackDuration"]),
        "position": parse_duration(fields["RelTime"]),
    }
    didl = html.unescape(fields["TrackMetaData"] or "")
    for key, tags in _DIDL_TAGS.items():
        info[key] = None
        for tag in tags:
            match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", didl, re.S)
            if match and (value := _clean(match.group(1))):
                info[key] = value
                break
    if info["duration"] == 0:
        info["duration"] = None
    return info


@dataclass(slots=True)
class GroupMember:
    """One speaker of a multichannel group."""

    device_name: str
    friendly_name: str
    channels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GroupInfo:
    """The multichannel group the speaker leads, if any."""

    layout: str | None
    members: list[GroupMember] = field(default_factory=list)


def parse_group_info(result: dict[str, Any]) -> GroupInfo | None:
    """Read getGroupInfo; None when the speaker is not part of a group."""
    info = result.get("group_info")
    if not isinstance(info, dict) or info.get("disabled"):
        return None
    group = info.get("group") if isinstance(info.get("group"), dict) else {}
    members = [
        GroupMember(
            device_name=str(member.get("device_name") or ""),
            friendly_name=str(member.get("friendly_name") or ""),
            channels=[str(c) for c in member.get("channel") or []],
        )
        for member in info.get("members") or []
        if isinstance(member, dict)
    ]
    layout = group.get("multichannelType") or _layout_from_combination(group.get("combination_id"))
    return GroupInfo(layout=layout, members=members)


def _layout_from_combination(combination_id: Any) -> str | None:
    """ "7.1.4_20df_20e1_208d_208d" -> "7.1.4"; some firmware reports only this."""
    match = re.match(r"(\d+\.\d+(?:\.\d+)?)_", str(combination_id or ""))
    return match.group(1) if match else None


class EnchantClient:
    """Talks to one speaker. The aiohttp session belongs to the caller."""

    def __init__(self, host: str, session: aiohttp.ClientSession, ssl_context: ssl.SSLContext) -> None:
        self.host = host
        self._session = session
        self._ssl = ssl_context
        self._limit = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)

    async def command(self, name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one httpapi command and return its JSON answer."""
        text = await self._post(
            name,
            f"https://{self.host}/httpapi.asp",
            build_command_body(name, payload),
            {"Content-Type": "application/x-www-form-urlencoded"},
            ssl_option=self._ssl,
        )
        return parse_command_response(name, text)

    async def soap(self, service: str, action: str, args: str = "") -> str:
        """Call a UPnP action and return the raw XML answer."""
        return await self._post(
            action,
            f"http://{self.host}:{UPNP_CONTROL_PORT}/upnp/control/{_SOAP_PATHS[service]}",
            _SOAP_ENVELOPE.format(service=service, action=action, args=args),
            {
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"urn:schemas-upnp-org:service:{service}:1#{action}"',
            },
            check_status=True,
        )

    async def _post(
        self,
        label: str,
        url: str,
        body: str,
        headers: dict[str, str],
        *,
        ssl_option: ssl.SSLContext | bool = True,
        check_status: bool = False,
    ) -> str:
        """POST once; send again once if the speaker closed a kept-alive connection."""
        for attempt in range(2):
            try:
                async with self._limit, asyncio.timeout(REQUEST_TIMEOUT):
                    async with self._session.post(url, data=body, headers=headers, ssl=ssl_option) as response:
                        text = await response.text(errors="replace")
                        if check_status and response.status != 200:
                            raise EnchantCommandError(f"{label}: HTTP {response.status}")
                        return text
            except aiohttp.ClientConnectorCertificateError as err:
                raise EnchantCertificateError(f"{self.host}: {err.certificate_error}") from err
            except _STALE_CONNECTION_ERRORS as err:
                if attempt:
                    raise EnchantConnectionError(f"{label}: {err!r}") from err
            except (TimeoutError, aiohttp.ClientError, OSError) as err:
                raise EnchantConnectionError(f"{label}: {err!r}") from err
        raise EnchantConnectionError(f"{label}: no answer")  # not reached

    async def fetch_image(self, path: str) -> tuple[bytes, str | None]:
        """Download an image the speaker serves itself, e.g. the AirPlay cover."""
        try:
            async with self._limit, asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.get(f"https://{self.host}{path}", ssl=self._ssl) as response:
                    if response.status != 200:
                        raise EnchantCommandError(f"{path}: HTTP {response.status}")
                    data = await response.read()
                    return data, image_content_type(data, response.headers.get("Content-Type"))
        except aiohttp.ClientConnectorCertificateError as err:
            raise EnchantCertificateError(f"{self.host}: {err.certificate_error}") from err
        except (TimeoutError, aiohttp.ClientError, OSError) as err:
            raise EnchantConnectionError(f"{path}: {err!r}") from err

    async def transport_info(self) -> dict[str, Any]:
        """What the speaker is playing, from UPnP AVTransport."""
        return parse_transport_info(await self.soap("AVTransport", "GetInfoEx"))

    async def set_volume(self, volume: int) -> None:
        """Set the volume, 0-100."""
        volume = max(0, min(100, int(volume)))
        await self.soap(
            "RenderingControl",
            "SetVolume",
            f"<Channel>Master</Channel><DesiredVolume>{volume}</DesiredVolume>",
        )

    async def set_mute(self, mute: bool) -> None:
        """Mute or unmute."""
        await self.soap(
            "RenderingControl",
            "SetMute",
            f"<Channel>Master</Channel><DesiredMute>{int(mute)}</DesiredMute>",
        )

    async def subscribe(
        self, service_path: str, callback_url: str | None, sid: str | None, timeout: int
    ) -> tuple[str, int]:
        """Create or renew a GENA subscription; returns (SID, granted seconds)."""
        headers = {"TIMEOUT": f"Second-{timeout}"}
        if sid:
            headers["SID"] = sid
        else:
            headers["CALLBACK"] = f"<{callback_url}>"
            headers["NT"] = "upnp:event"
        url = f"http://{self.host}:{UPNP_EVENT_PORT}/upnp/event/{service_path}"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request("SUBSCRIBE", url, headers=headers) as response:
                    if response.status != 200:
                        raise EnchantCommandError(f"SUBSCRIBE {service_path}: HTTP {response.status}")
                    new_sid = response.headers.get("SID") or sid
                    granted = response.headers.get("TIMEOUT", "")
        except (TimeoutError, aiohttp.ClientError, OSError) as err:
            raise EnchantConnectionError(f"SUBSCRIBE {service_path}: {err!r}") from err
        if not new_sid:
            raise EnchantCommandError(f"SUBSCRIBE {service_path}: no SID")
        match = re.search(r"Second-(\d+)", granted)
        return new_sid, int(match.group(1)) if match else timeout

    async def unsubscribe(self, service_path: str, sid: str) -> None:
        """End a GENA subscription; errors are ignored."""
        url = f"http://{self.host}:{UPNP_EVENT_PORT}/upnp/event/{service_path}"
        try:
            async with asyncio.timeout(5):
                async with self._session.request("UNSUBSCRIBE", url, headers={"SID": sid}):
                    pass
        except (TimeoutError, aiohttp.ClientError, OSError):
            pass
