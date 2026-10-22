# Changelog

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
