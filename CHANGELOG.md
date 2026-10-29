# Changelog

## 0.1.0

First release.

- Media player: power, volume, mute and input selection (TV, HDMI, Bluetooth).
- Equalizer: the seven bands of the custom equalizer and the preset selection.
- Atmos level (Low, Mid, High), audio sync and sleep timer.
- Switches: Smart mode, Listen mode, PureVoice and feedback tones (the last two disabled by default).
- Sensors: audio format of the TV input, playing source, sleep timer remaining, surround layout.
- Binary sensor: Dolby Atmos.
- Buttons: start the sound calibration (soundbar), start or stop the Moment (Enchant Speaker).
- AirPlay, Google Cast, Spotify and DLNA playback: shown as the input, with title, artist, album, artwork and position, and play, pause, next and previous track.
- Track changes and volume changes show up at once through the speaker's UPnP events.
- Icons for the sound settings and sensors.
- Entities depend on the model: Enchant 1100 / 900 soundbars and the Enchant Speaker each get only what they handle.
- Automatic discovery on the local network; only Enchant speakers are accepted. The Enchant Sub is used through its soundbar and is not added on its own.
- Brand images for the Home Assistant interface.
- Dashboard card (`custom:harman-enchant-card`), loaded by the integration: now playing with artwork, controls, volume, inputs, and tabs for the sound settings, the equalizer with its curve, the sleep timer and the group information. It shows only what the speaker has.
