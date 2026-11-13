# Render backend

```sh
sv2cli render song.svp --stems -o stems --warmup 30 --timeout 1800
sv2cli render song.svp --track "#1" -o lead.wav
sv2cli render song.svp --stems -o stems --bit-depth 24
```

The native backend uses the [direct VST3 transport](../native/README.md) to load
the installed **Synthesizer V Studio 2 Plugin.vst3**. Build `native/` and set
`SV2CLI_NATIVE_HOST` or profile `native_host` to its shared library. Source
checkouts also discover a library in `native/`, `native/build/Release/` or
`native/build/`. Portable packages discover their adjacent `runtime/` library. It obtains
the public JUCE state, replaces only the project envelope and preserves opaque
bytes. Python verifies the loaded score before allowing playback. No engine
binary inspection, engine patching or UI automation is used.

The plugin and voice must be installed and activated in a desktop session. A
hidden temporary editor commits plugin state during initialization; plugin-owned
activation/error dialogs are not automated. The parent never loads native code:
the disposable worker owns the library, plugin and its threads.

The plugin exposes multiple output channels. The first stereo pair is the master bus; extra track buses are not averaged into it. Stem jobs render each selected track on its own. Existing gain, pan, mute and effects are honored. Explicit track selection removes unrelated solo flags; whole-project rendering retains the original solo/mute state. Stem export uses the track's gain/pan/effects; use an edit recipe to bypass them if desired.

Only the main stereo bus is recorded in memory, rather than all of the plugin's output channels. Render copies also omit library groups that none of the selected tracks references; the source file's library is preserved. For long choir projects, prefer sequential stems to loading every choir member at once, then sum the stems on their original time axis without applying their mixer gain/pan/effects a second time.

Only PCM16/24 mono/stereo main audio is written. Native aspiration, pitch export
and ARA output are not simulated. CLI format flags control the WAV. Duration is
score-end seconds plus `--tail`. Tempo and meter maps use integer sample
boundaries; tempo changes no longer require a 1/960-quarter grid. Nonzero SVP
`startTimeSeconds` is explicitly rejected pending independent validation.

Warmup dispatches messages while the transport is stopped. Production then
performs **exactly one render pass**: the owning message thread processes one
audio block, dispatches messages with the sample position held fixed, then
advances the integer clock. The main stereo bus is recorded directly, without
the old graph-rendering path. There are no envelope-convergence passes, waveform
error retries, priming renders or automatic timing translations.

`--attempts` accepts only `1`; larger values fail before launching a worker.
`--single-pass` remains an inert compatibility flag. A silent, incomplete or late
render fails and preserves evidence. The code never rerenders to find a lucky
acceptable pass. Fixed-count repeated runs in validation retain every result
and are not a production acceptance strategy.

Native renders measure the first isolated waveform entry and default to
`--entry-policy report`. The timing report accompanies the exported audio.
Breaths and consonants can begin before the written note. Use
`--entry-policy check` to enforce `--entry-tolerance 0.03`, or
`--entry-policy align` to translate a reviewed whole-recording offset.
Use `--stems` to measure individual tracks. See [entry alignment](wave-align.md).

Main groups use the plugin's open-ended reference range. Render snapshots also
normalize ranges written by older CLI versions, which could silence new tracks.

For a word with an early unvoiced consonant, choose `--entry-landmark voiced`
explicitly after inspection. It checks low-band voicing energy and retains the
broadband evidence. `entry-check` can inspect a retained raw WAV with either
landmark without rendering or moving any audio. The choice is included in the
resume fingerprint; the code never tries landmarks automatically until one
passes.

Each output has a manifest with numerical audio checks. Silence, no samples, short files, non-finite data and excessive clipping cause a failure before the final filename is written. Worker logs and project copies are kept under `.sv2cli-jobs/<job-id>/`; they can contain project lyrics and local paths and should not be published accidentally.

The manifest is checkpointed before work and after each successful track.
`--resume` reuses verified completed files after SHA-256, format and audio checks.
The project, CLI version, backend settings, native-library SHA-256 and entry
policy must match. A failed task is not automatically retried; an explicit user
invocation may resume partial work. Externally edited outputs are protected.
`--force` explicitly starts fresh; it cannot be combined with `--resume`.

Each checkpoint emits a JSON `render_progress` event to stderr with completed/total tasks, active track names and errors. `sv2cli job-status stems` (or a WAV/manifest path) reads compact persistent status, including reused/skipped/failed work. Progress reports task counts, not an invented time estimate. The companion skill uses these signals in a measured edit/render/check/rollback feedback loop and incorporates user corrections into task-local acceptance criteria.

Stem jobs skip empty, muted and render-disabled tracks and report them in `skipped`. A failed job can leave verified successful WAVs with a failed manifest; they are partial output, not a completed delivery. Progress checkpoints make these files resumable.

`coverage.json` records the single pass's expected and missing activity windows.
Incomplete native audio remains as the raw job WAV; it is never copied to the
requested final output. The manifest reports `renderPassesPerTask: 1`,
`automaticRetries: false` and `convergenceRequired: false`.

Long WAV validation uses bounded vectorized chunks when NumPy is available (as it is for native renders). The dependency-free path remains available with the same format, silence, duration, nonfinite-sample and clipping checks.

The parent terminates only its owned render worker on timeout or cancellation. It does not terminate an already-open Studio or delete Dreamtonics caches. A native plugin crash becomes a backend error with the retained log.

If rendering fails, inspect the retained log, state and coverage/entry evidence.
Resolve the cause before explicitly starting another job. Unknown state layouts
fail with `unsupported_plugin_state`. A missing native library fails clearly;
there is no fallback to the old drifting DawDreamer host.
