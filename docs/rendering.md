# Render backend

```sh
sv2cli render song.svp -o mix.wav --warmup 30 --attempts 6 --timeout 1800
sv2cli render song.svp --track "#1" -o lead.wav
sv2cli render song.svp --stems -o stems --bit-depth 24
```

The native backend uses DawDreamer to load the installed **Synthesizer V Studio 2 Plugin.vst3** instrument. It obtains that plugin's public JUCE state, replaces the JSON `projectContent` envelope with a project copy, and preserves opaque state bytes. It supplies a host tempo map and dispatches the host thread's application messages while rendering on an audio thread. No screenshots, mouse/keyboard simulation, engine binary inspection or engine patching is used.

This is a desktop-plugin host, not a replacement synthesis engine. It still needs installed/activated products and an available desktop session. DawDreamer's `load_state` creates a temporary editor as part of plugin initialization; a window may briefly appear. `CREATE_NO_WINDOW` hides the worker console on Windows, not every possible plugin-owned dialog. Authentication or activation dialogs are never automated.

The plugin exposes multiple output channels. The first stereo pair is the master bus; extra track buses are not averaged into it. Stem jobs render each selected track on its own. Existing gain, pan, mute and effects are honored. Explicit track selection removes unrelated solo flags; whole-project rendering retains the original solo/mute state. Stem export uses the track's gain/pan/effects; use an edit recipe to bypass them if desired.

Only the main stereo bus is recorded in memory, rather than all of the plugin's output channels. Render copies also omit library groups that none of the selected tracks references; the source file's library is preserved. For long choir projects, prefer sequential stems to loading every choir member at once, then sum the stems on their original time axis without applying their mixer gain/pan/effects a second time.

Only PCM16/24, mono/stereo main audio is written. Native `renderConfig` aspiration settings, native pitch export and ARA output are not simulated. The CLI's format flags control VST3 output; changing `renderConfig` alone does not change those flags. VST3 output duration is score-end seconds plus `--tail` (default 2 seconds); long reverb may need a longer tail. Tempo marks must fit a 1/960-quarter host grid.

Async synthesis is warmed up, then rendered repeatedly. Each pass must have nonzero audio and activity inside expected audible note windows. Two passes need sufficiently similar **one-second RMS envelopes**. A raw-sample comparison would falsely reject valid synthesized noise/phase variation; short envelope windows also fluctuate with choir phase beating. Note activity windows independently check shorter silent gaps. These checks detect obvious incomplete/silent output, not every missing voice in a dense mix; stems are the better validation unit. `--single-pass` deliberately disables convergence and should be used only for diagnosis.

Each output has a manifest with numerical audio checks. Silence, no samples, short files, non-finite data and excessive clipping cause a failure before the final filename is written. Worker logs and project copies are kept under `.sv2cli-jobs/<job-id>/`; they can contain project lyrics and local paths and should not be published accidentally.

`coverage.json` records the latest pass's expected and missing activity windows. A nonzero but incomplete render reports `incomplete_audio` and retains diagnostic `incomplete-audio.npy`; it is never copied to the requested final output.

The parent terminates only its owned render worker on timeout or cancellation. It does not terminate an already-open Studio or delete Dreamtonics caches. A native plugin crash becomes a backend error with the retained log.

If rendering fails, inspect `worker.log`, check activation in Studio, try a short project with the same bank, and increase warmup/attempts if inference is slow. Unknown plugin-state layouts fail with `unsupported_plugin_state`; do not force arbitrary bytes into a new plugin version.
