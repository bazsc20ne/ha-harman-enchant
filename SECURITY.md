# Security policy

## Reporting a problem

Please report security problems privately, not in a public issue: open the
repository's **Security** tab and choose **Report a vulnerability**
(<https://github.com/bazsc20ne/ha-harman-enchant/security/advisories/new>).
Only the maintainer sees the report until a fix is released.

Fixes are made in the latest release only.

## What the integration checks

- When a speaker is added, the integration records the speaker's server
  certificate. Every later connection to the speaker's command interface must
  present the same certificate. If it changes, Home Assistant asks whether to
  accept the new one.
- Event notifications are accepted only from the speaker's address.

## Out of scope

- The TLS client certificate in `custom_components/harman_enchant/certs/` is the
  same for every speaker and is public (see [NOTICE](NOTICE)). It is not a secret
  of this project.
- The speakers' UPnP interface has no authentication: any device on the local
  network can control playback and volume. This is how the speakers work, and the
  integration cannot change it.
