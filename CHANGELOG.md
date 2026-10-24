# Changelog

## 0.3.0.dev1

- Include every positive-duration note in activity coverage; reject unexpected score-active RMS silence and out-of-audio windows.
- Add located vocal preflight and explicit MIDI polyphony split/top/reject policies, FIFO overlap truncation, channel separation, default lyrics and charset.
- Fix simultaneous MIDI lyric/note ordering; use exact rational MIDI tick conversion.
- Add SV2 rigid expression and score-preserving native flat curves, optional explicit articulation, and plugin readback verification of tuning/effects.
- Add explicit sample-peak normalization, dBFS metrics, validated nested effect schemas and an effects command.
- Keep stems on the complete shared timeline; preserve worker error codes; invalidate resume across CLI/acceptance versions.
- Validate meter maps and known expression attributes; report actual runtime paths in doctor.
- Preserve the single-pass/no-automatic-retry architecture. Full commands and measured boundaries: docs/feedback-fixes.md.


## 0.3.0.dev0 — 2026-10-25 (local development)

- Replace the drifting DawDreamer graph path with a direct VST3 host using an integer sample clock and message-thread block processing.
- Exactly one native render pass per task; remove readiness-convergence render loops and reject retry requests before a worker is launched.
- Preserve public state-envelope adaptation, loaded-score verification, main-bus routing, isolation, format/activity checks and checkpointed resume.
- Split tempo/meter changes at sample boundaries; reject unverified nonzero time origins instead of silently shifting them.
- Include native-library SHA-256 in resume identity; require a configured native host with no legacy fallback.
- Retain measured entry acceptance and explicit post-render correction as separate operations; no automatic PCM translation is part of the native transport.
- Add explicit `entry-check` and broadband/voiced landmark selection, preserving consonant lead-in evidence instead of moving already aligned vowels.
- The Python core remains MIT; the separately built JUCE-linked native host is AGPL-3.0-or-later.

## 0.2.0 — 2026-10-22

- Explicit in-place SVP editing with atomic replacement, source-change detection and timestamped backups; voice/mixer dry-runs.
- Reference-local edits for linked groups, UUID resolution before cloning, nonempty edit selection, strict recipe envelopes and schema inventory.
- Musical coordinates (bar/beat, seconds, fractional quarters), group/reference listing, isolated-stem timing diagnostics and guarded PCM audio shifts.
- Checkpointed render manifests, verified resume, and empty/muted/disabled stem skip reporting.
- Structured render progress and `job-status` for agent feedback loops.
- Correct MIDI track selection, inherited batch profiles, per-task input error handling and effective-pitch validation.
- Separate companion production skill: https://github.com/White-Wolf-233/sv2cli-skill.

## 0.1.0 — 2026-10-14

- Portable SVP inspection, conservative format repairs, new projects and score-aware diffs.
- Transactional recipes for voices/languages/dictionaries, notes, groups, tracks, mixer/effects, tempo/meters, automation, pitch controls and existing Retakes.
- Complete default/group singer switching and shared-group copy-on-write.
- Non-clobbering outputs, protected input files and explicit score-edit opt-in.
- VST3 rendering through the user's installed instrument plugin, with host tempo and application event-loop support.
- Mix/track/stem rendering, PCM16/24, mono/stereo, worker isolation, progress, convergence/activity checks, timeout and audio reports.
- Named machine profiles, custom argv render backend, MIDI/CSV conversion and batch jobs.
- Optional local Lua bridge for computed engine data, playback and Retakes.
- English/Chinese documentation, complete feature inventory and multi-platform core CI.
