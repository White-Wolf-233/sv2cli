# Validation

Validation separates project/transport checks from synthesis and listening.

## Automated core tests

`python -m pytest -q` covers conservative repair, native flat automation, absolute group ranges, shared-group isolation, score protection, exact-track selection, no-clobber writes, transactional failure, voice inheritance/overrides, MIDI/CSV roundtrips and timing-loss rejection, guarded JSON Patch, Lua execution, mailbox expiration, a real subprocess adapter, WAV silence/duration checks, and phase-independent render readiness.

GitHub Actions runs the core suite on Windows/macOS/Linux × Python 3.10/3.12/3.13, builds distributions and checks CLI installation. These jobs do not contain licensed Synthesizer V plugins or voices.

## Native synthesis

Local environment: Windows 11, Python 3.12.10, DawDreamer 0.9.0, Synthesizer V Studio 2 Pro / instrument plugin 2.2.1, Kasane Teto AI 2.

An independent three-note G2/B2/D3 probe rendered through the CLI as an 8-second stereo PCM16 WAV. Peak approximately 0.129, RMS approximately 0.0199, no clipping, with activity in each expected note window. The extra duration contains the requested render tail. Native plugin processing is real; it is not a fake backend or an old Studio export.

The user's existing full ten-track project (3277 notes) passes structural validation; its source file is unchanged. Private song projects, audio and absolute machine paths are excluded from Git and release packages.

Further native-render results are recorded in `validation-summary.json`. macOS native plugin rendering and in-editor Lua live integration remain unverified here. Lua syntax/dispatch and mailbox behavior use explicit mocks; a command-adapter test uses a synthetic sine generator and is not voice synthesis.

No subjective audition or claim of matching a reference recording is made by these numerical checks.
