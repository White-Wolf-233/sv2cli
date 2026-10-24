# Validation

## 0.3.0.dev0 direct-host validation (2026-10-25)

The Python suite passes 116 tests locally. It now covers exact tempo/meter sample
maps, off-960-grid tempo marks, rejected nonzero origins, missing-host errors
without fallback, loaded-score callback ordering, duplicate-pass rejection,
entry gates/corrections, explicit low-band landmarks that preserve consonant
lead-ins while rejecting shifted carriers, and retry rejection before launch.

The native host was built locally with MSVC 19.44 and JUCE 8.0.6 on Windows.
The same six-note S and A openings each produced a 9.482 s first RMS attack in
four fixed validation passes; the written entry is 9.473684 s. No translation
was applied. Restoring old clock-context flags in a direct-host control also
remained stable, so no particular flag is claimed as the dependency's root bug.
The replacement bypasses the old DawDreamer hosting path entirely.

Fresh CLI workers also rendered the complete S, A and T parts once each with
the original tempo/meter maps, zero missing expected activity windows and
unshifted first attacks at 9.482, 9.482 and 9.480 s. Seventeen later measurable
shared S/A phrase entries differ by 0–30 ms. This is waveform-energy evidence;
all-note/phoneme timing and subjective listening remain separate.

All seven actual vocal tracks were subsequently rendered in fresh workers,
once per track, including later divisi entries. All expected activity windows
were present. A2 and B2 were initially rejected by the broadband entry gate
because their consonants precede the vowel beat. Their **same retained PCM** was
inspected and checked with the explicit voiced-energy landmark, yielding
+2.105 ms and -1.895 ms respectively. No rerender, shift, threshold relaxation
or time stretch was used. Both broadband failures and the separate review
evidence were retained. These are distinct acoustic landmarks, not identical
claims about first sound versus vowel entry.

Historical convergence-based results below describe older versions. They are
not the current production acceptance strategy. Current production performs one
pass and fails visibly on incomplete or out-of-tolerance audio.

## 0.2.0 validation (2026-10-22)

The Windows/Python 3.12 core suite now contains 96 passing tests. New regression checks exercise same-track/cross-track repeated references at different offsets, UUID selectors across multi-step recipes, effective pitch limits, MIDI selection, batch profile inheritance, source overwrite/backup/failed atomic replacement, bar/beat/seconds conversion, missing/late activity, audio shift regression/crop rejection, checkpoint failure/resume and modified-output conflict recovery. Cross-platform CI is separate from this local result.

The current three-note Teto VST3 probe produced a real 5-second 44.1 kHz stereo PCM24 WAV (peak 0.1586995125, RMS 0.0282193177, zero clipped samples). Two render passes converged, all three activity windows were present, and the loaded score matched. The timing diagnostic measured an energy-entry proxy about 190 ms after the first written onset and explicitly left connected boundaries unresolved; this is not a phoneme alignment measurement. Injecting a known 100 ms delay into that real WAV and correcting it through `audio-shift` restored every original PCM sample exactly, with all note activity retained. No new subjective audition or full-song acceptance is claimed.

The independent production skill passes its metadata validator and executes its packaged recipe, protected overwrite, musical-time and delayed-signal correction smoke. These checks do not establish model routing quality or subjective musical success.

Validation separates project/transport checks from synthesis and listening.

## Automated core tests

`python -m pytest -q` covers conservative repair, native flat automation, absolute group ranges, shared-group isolation, score protection, exact-track selection, no-clobber writes, transactional failure, voice inheritance/overrides, MIDI/CSV roundtrips and timing-loss rejection, guarded JSON Patch, Lua execution, mailbox expiration, a real subprocess adapter, WAV silence/duration checks, and phase-independent render readiness.

GitHub Actions runs the core suite on Windows/macOS/Linux × Python 3.10/3.12/3.13, builds distributions and checks CLI installation. These jobs do not contain licensed Synthesizer V plugins or voices.

## Native synthesis

Local environment: Windows 11, Python 3.12.10, DawDreamer 0.9.0, Synthesizer V Studio 2 Pro / instrument plugin 2.2.1, Kasane Teto AI 2.

An independent three-note G2/B2/D3 probe rendered through the CLI as an 8-second stereo PCM16 WAV. Peak approximately 0.129, RMS approximately 0.0199, no clipping, with activity in each expected note window. The extra duration contains the requested render tail. Native plugin processing is real; it is not a fake backend or an old Studio export.

The user's existing full ten-track project (3277 notes) passes structural validation; its source file is unchanged. Private song projects, audio and absolute machine paths are excluded from Git and release packages.

An eight-track excerpt with 168 original notes and four choir members per track also rendered through the CLI. The 16.769-second stereo PCM24 result has peak 0.128647, RMS 0.0206412 and zero clipped samples. All 142 expected audible note windows were active in the accepted passes; one-second energy-envelope error was 0.000637. The loaded score was read back through the plugin state and matched the requested excerpt. This is a short excerpt, not proof of a completed full-song export or subjective reference match.

Further native-render results are recorded in `validation-summary.json`. macOS native plugin rendering and in-editor Lua live integration remain unverified here. Lua syntax/dispatch and mailbox behavior use explicit mocks; a command-adapter test uses a synthetic sine generator and is not voice synthesis.

The explicit singer-switch pipeline was also exercised with the installed Teto bank: Mandarin/xsampa overrides and score identity were retained while Gender changed. The numbered mono PCM24 stem rendered successfully (8 seconds, peak 0.127554, RMS 0.0199625, no clipping). Median YIN-style F0 estimates for MIDI 43/47/50 were 97.351/123.184/146.756 Hz, consistent with G2/B2/D3 rather than octave-raised notes. Switching to a different installed singer remains untested because this machine only supplies this bank.

No subjective audition or claim of matching a reference recording is made by these numerical checks.
