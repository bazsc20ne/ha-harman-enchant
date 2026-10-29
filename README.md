# Harman Kardon Enchant for Home Assistant

A Home Assistant custom integration for the **Harman Kardon Enchant** speakers.
It talks to the speaker on your local network only. No cloud account is needed,
and the vendor app does not have to run in the background.

## Supported models

| | Enchant 1100, Enchant 900 | Enchant Speaker |
| --- | --- | --- |
| Media player: power, volume, mute, playback state, now playing | yes | yes |
| Input selection (TV, HDMI, Bluetooth) | yes | – |
| Equalizer bands and presets | yes | yes |
| Atmos level, Smart mode, Listen mode, PureVoice, feedback tones, audio sync | yes | – |
| Sleep timer | yes | yes |
| Calibrate | yes | – (it calibrates itself) |
| Moment | – | yes |
| TV audio format, Dolby Atmos | yes | – |
| Playing source | yes | yes |
| Surround layout | yes | – |

Only the entities the speaker supports are created; the sound settings are listed
under the device's *Configuration* section.

Tested with the **Enchant 1100**, on its own and leading a 7.1.4 group with an
Enchant Sub and two Enchant Speakers, and with the **Enchant Speaker** on its own.
The Enchant 900 is handled like the Enchant 1100 but has not been tested yet;
reports are welcome in the issue tracker.

The **Enchant Sub** works only through the soundbar it is paired with, so it is not
added on its own. When the speakers are grouped into a surround system in the
Harman Kardon One app, only the soundbar that leads the group is on your network:
add that one, it controls the whole group.

## What the entities do

### Media player

- **Power** switches the speaker on or to standby. The speaker also goes to standby
  by itself after about 10 minutes without activity, and it wakes up by itself,
  for example when the TV connected over HDMI eARC is switched on. The media player
  follows these changes.
- **Input** selects *TV* (the TV connection: HDMI eARC/ARC or optical), *HDMI*
  (the HDMI input of the soundbar) or *Bluetooth*.
- **Now playing**: while AirPlay, Google Cast, Spotify or DLNA plays, the media player
  shows the service as its input, and the title, artist, album, artwork, length
  and position of the track, as far as the service sends them. Play, pause, next
  track and previous track work like the keys in the Harman Kardon One app. A new
  track shows up within a second; its artwork can follow one or two seconds
  later, as the speaker updates it after the title.

  | Source | Input shown | Artwork |
  | --- | --- | --- |
  | AirPlay (also from Music Assistant) | AirPlay | the cover the speaker receives over AirPlay |
  | Google Cast | Google Cast | the cover the casting app sends, e.g. YouTube Music |
  | Spotify Connect | Spotify | the cover Spotify sends |
  | DLNA | DLNA | the cover the DLNA controller sends, if any |

  Other streaming services the speaker supports, for example Roon or TIDAL
  Connect, show up with the name the speaker reports. The speaker does not report
  which app is casting, so YouTube Music and other Cast apps all show up as
  Google Cast. AirPlay works out of the box; Google Cast has to be turned on for
  each speaker in the Harman Kardon One app first.
- **Volume** and **mute** control the speaker's volume.

### Sound

- **Equalizer bands**: the seven sliders of the *Edit Equalizer* screen in the
  Harman Kardon One app, from -6 to +6 dB in 0.5 dB steps. They belong to the
  *Custom* preset, so changing a band also selects that preset.
- **Equalizer preset**: Signature Sound, Vocal, Energetic, Chill or Custom.
- **Atmos level**: the strength of the height effect for Dolby Atmos and DTS:X
  content: Low, Mid or High, as the soundbar display shows them (Mid is the
  factory setting). It has no effect on other content, except
  Dolby Digital 5.1 and 7.1, which the soundbar can expand to 3D sound.
- **Smart mode**: when on, the soundbar adds its own sound processing (equalizer
  and surround) for a richer sound. When off, it plays in *Standard mode* with the
  plain preset equalizer, which suits speech such as news. Smart mode is on by
  default, and the soundbar turns it back on every time it is switched on.
- **Listen mode**: when on, the subwoofer and the surround speakers play
  noticeably quieter while the soundbar keeps its level, and PureVoice is turned
  off. When the mode is turned on or off, the soundbar briefly shows
  *ON LISTEN MODE* or *OFF LISTEN MODE* on its display. The Harman Kardon One app
  has no switch for it.
- **PureVoice**: Harman's dialogue enhancement, which keeps speech easy to follow.
  The app does not show it as a separate setting. The speaker turns PureVoice off
  when Listen mode is turned on, when Smart mode is turned off, and on the
  Bluetooth input, and it does not always turn it back on afterwards. The switch is disabled by default; enable it in the
  device's entity list if you want to control it.
- **Feedback tones**: a setting the speaker reports. In tests no difference was
  heard with it on or off when muting, changing the volume or the input,
  switching the speaker on and off, or pressing the Moment key, so the switch is
  disabled by default.
- **Audio sync**: delays the sound by 0 to 250 ms so that it matches the picture,
  like the audio sync setting of the remote control and the app.

### Timer

- **Sleep timer**: switches the speaker to standby after the given number of
  minutes. 0 turns the timer off.
- **Sleep timer remaining**: minutes left until the sleep timer switches the
  speaker off.

### Buttons

- **Moment** (Enchant Speaker): starts or stops the Moment set up in the Harman
  Kardon One app, for example a nature sound or a playlist, like the Moment key on
  the speaker. The speaker does not report whether a Moment is playing.
- **Calibrate** (soundbar): starts the sound calibration, the same as the CALIBRATION key of
  the remote control. The speakers play test tones for about a minute, and the
  soundbar shows *CALIBRATION* and then *DONE* on its display. The speaker does
  not report the progress or the result.

### Information

- **TV audio format**: the format of the audio coming from the TV, for example
  `Dolby Digital Plus / Dolby Surround / 8ch / 48 kHz` or `PCM / 2ch / 48 kHz`.
  The speaker reports it only when it changes, so after a restart of Home
  Assistant the sensor stays unknown until the next change. It is also unknown
  when there is no signal.
- **Dolby Atmos**: on while Dolby Atmos audio plays.
- **Playing source**: what the speaker is playing right now, for example *TV*,
  *HDMI*, *Bluetooth*, *AirPlay* (also when Music Assistant plays to the speaker
  over AirPlay), *Google Cast*, *Spotify* or *DLNA*; *Idle* when nothing plays and
  *Other* for anything else. The *Source name* attribute shows the name the
  speaker reports.
- **Surround layout**: the channel layout of the speaker group, for example
  `7.1.4`. Its attributes list the members of the group and their channels.

### Not supported

The bass level and the level of the surround speakers can be changed with the
remote control and in the app, but the speaker does not report them over its
local interface, so the integration cannot show or change them.

## Dashboard card

The integration comes with its own dashboard card. There is nothing to download
or to add under *Resources*; after installing or updating the integration, reload
the dashboard once in the browser or the app.

Add it with **Edit dashboard → Add card → Harman Kardon Enchant**, or in YAML:

```yaml
type: custom:harman-enchant-card
entity: media_player.enchant_1100
```

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/card_equalizer.png" alt="Harman Kardon Enchant card, Equalizer tab, in the light and the dark theme" width="972">

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/card_sound.png" alt="Harman Kardon Enchant card, Sound tab, in the light and the dark theme" width="972">

Point it at the media player of the speaker. The card finds the other entities of
that speaker by itself and shows only what the speaker has, so the same card
works for the soundbar and for the Enchant Speaker:

- The artwork, title, artist and album of what plays, the playing source (for
  example TV, AirPlay or Spotify), a *Dolby Atmos* badge while Dolby Atmos plays,
  and the power button.
- The track position, play/pause, previous and next while a streaming service
  plays, and the Moment button on the Enchant Speaker.
- Volume and mute, and the input buttons of the soundbar.
- **Sound**: Atmos level, Smart mode, Listen mode, PureVoice and feedback tones
  (when enabled), audio sync, and Calibrate, which asks for a second tap before
  the test tones start.
- **Equalizer**: the presets and the seven bands as sliders with the resulting
  curve.
- **Timer**: sleep timer presets and the time left.
- **Info**: playing source, TV audio format, Dolby Atmos, and the surround
  layout with the channels each speaker of the group plays.

Disabled entities are left out.

The card follows the active Home Assistant theme: its colours, fonts and corners
come from the theme, in light and in dark mode alike. The screenshots show the
default theme, light on the left and dark on the right; the built-in cards below
behave the same way.

| Option | Description |
| --- | --- |
| `entity` | Required. The media player of the speaker. |
| `name` | Name shown while nothing plays. Default: the name of the device. |
| `hide` | Parts to leave out: `volume`, `inputs`, `sound`, `equalizer`, `timer`, `info`. |

### Cards built into Home Assistant

The entities also work with the cards that come with Home Assistant. In the
examples below, replace `enchant_1100` (soundbar) or `enchant_speaker` (Enchant
Speaker) with the beginning of your own entity ids, as shown on the device page.
The `name` lines are optional; without them the cards show the full entity names.

<details>
<summary>Now playing, with artwork (soundbar and speaker)</summary>

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/builtin_media_control.png" alt="Media control card in the light and the dark theme" width="972">

```yaml
type: media-control
entity: media_player.enchant_1100
name: Enchant 1100
```

A smaller version with playback and volume controls:

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/builtin_tile.png" alt="Tile card with playback and volume controls in the light and the dark theme" width="532">

```yaml
type: tile
entity: media_player.enchant_1100
name: Enchant 1100
show_entity_picture: true
state_content:
  - media_title
  - media_artist
features:
  - type: media-player-playback
  - type: media-player-volume-slider
```

</details>

<details>
<summary>Input (soundbar)</summary>

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/builtin_input.png" alt="Tile card with the input selector in the light and the dark theme" width="532">

```yaml
type: tile
entity: media_player.enchant_1100
name: Input
hide_state: true
features:
  - type: media-player-source
```

</details>

<details>
<summary>Sound settings (soundbar)</summary>

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/builtin_sound.png" alt="Tile cards for the sound settings in the light and the dark theme" width="972">

```yaml
type: grid
columns: 2
square: false
cards:
  - type: tile
    entity: select.enchant_1100_equalizer_preset
    name: Equalizer preset
    features:
      - type: select-options
  - type: tile
    entity: select.enchant_1100_atmos_level
    name: Atmos level
    features:
      - type: select-options
  - type: tile
    entity: switch.enchant_1100_smart_mode
    name: Smart mode
    features:
      - type: toggle
  - type: tile
    entity: switch.enchant_1100_listen_mode
    name: Listen mode
    features:
      - type: toggle
  - type: tile
    entity: number.enchant_1100_audio_sync
    name: Audio sync
    features:
      - type: numeric-input
  - type: tile
    entity: button.enchant_1100_calibrate
    name: Calibrate
    hide_state: true
    tap_action:
      action: perform-action
      perform_action: button.press
      target:
        entity_id: button.enchant_1100_calibrate
      confirmation:
        text: The speakers play test tones for about a minute. Start the calibration?
```

</details>

<details>
<summary>Equalizer (soundbar and speaker)</summary>

<img src="https://raw.githubusercontent.com/bazsc20ne/ha-harman-enchant/main/docs/images/builtin_equalizer.png" alt="Entities card with the equalizer in the light and the dark theme" width="972">

```yaml
type: entities
title: Equalizer
entities:
  - entity: select.enchant_1100_equalizer_preset
    name: Preset
  - entity: number.enchant_1100_equalizer_125_hz
    name: 125 Hz
  - entity: number.enchant_1100_equalizer_250_hz
    name: 250 Hz
  - entity: number.enchant_1100_equalizer_500_hz
    name: 500 Hz
  - entity: number.enchant_1100_equalizer_1_khz
    name: 1 kHz
  - entity: number.enchant_1100_equalizer_2_khz
    name: 2 kHz
  - entity: number.enchant_1100_equalizer_4_khz
    name: 4 kHz
  - entity: number.enchant_1100_equalizer_8_khz
    name: 8 kHz
```

</details>

<details>
<summary>Moment (Enchant Speaker)</summary>

```yaml
type: tile
entity: button.enchant_speaker_moment
name: Moment
hide_state: true
tap_action:
  action: perform-action
  perform_action: button.press
  target:
    entity_id: button.enchant_speaker_moment
```

</details>

## Requirements

- Home Assistant 2026.9 or newer.
- The speaker is set up with the Harman Kardon One app and connected to your network.
- Home Assistant can reach the speaker on TCP ports 443 and 59152, and the speaker
  can reach Home Assistant (for event notifications such as the audio format). If
  they are in different VLANs, allow this traffic in your firewall.

## Installation

### HACS

1. In HACS, open the menu, choose **Custom repositories**, and add
   `https://github.com/bazsc20ne/ha-harman-enchant` with the type **Integration**.
2. Search for **Harman Kardon Enchant** and download it.
3. Restart Home Assistant.

### Manual

Copy `custom_components/harman_enchant` into the `custom_components` folder of your
Home Assistant configuration and restart Home Assistant.

## Setup

Speakers are discovered automatically on the network. You can also add one by hand:
**Settings → Devices & services → Add integration → Harman Kardon Enchant**, then
enter the speaker's IP address. A fixed IP address (DHCP reservation) is
recommended.

## How it works

The speakers offer a local HTTPS command interface that only accepts clients with a
known TLS client certificate, plus standard UPnP for volume, mute and event
notifications. The integration polls the speaker every 10 seconds and listens for
its UPnP events, so that track, volume and audio format changes show up at once.

The client certificate in `custom_components/harman_enchant/certs/` is the one the
vendor app uses; see [NOTICE](NOTICE) for where it comes from.

When a speaker is added, the integration records the speaker's own server
certificate, and later connections are accepted only if the speaker presents the
same one. If it changes, the speaker stops working in Home Assistant until you
confirm the new certificate under **Settings → Devices & services**. Confirm it
only if you know why it changed; otherwise another device may be answering at the
speaker's address. Event notifications are accepted only from the speaker's
address.

## Security

Please report security problems privately, as described in
[SECURITY.md](SECURITY.md).

## Disclaimer

This project is not affiliated with, endorsed by or sponsored by Harman
International Industries or Harman Kardon. Harman Kardon and Enchant are
trademarks of Harman International Industries, Incorporated, and the logo is used
only to show which products the integration works with.

## License

[GNU Affero General Public License v3.0](LICENSE). Third-party material is listed in
[NOTICE](NOTICE).
