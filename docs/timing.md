# Musical time, actual audio timing and overwrites

These are separate operations: changing written onset/duration, measuring actual vocal timing, and matching a reference performance. Score identity and a nonempty WAV do not establish audible alignment.

## Coordinates and selection

```sh
sv2cli time song.svp --at bar:53:1
sv2cli time song.svp --at q:7/2
sv2cli time song.svp --at s:24.5
sv2cli groups song.svp --track '#2'
sv2cli notes song.svp --track '#2' --start bar:53:1 --end bar:61:1
```

`b:` is integer blicks, `q:` quarter notes (fractions allowed), `s:` project seconds including startTimeSeconds. `bar:N:BEAT` uses one-based bars and denominator-note beats (six eighth-note beats in 6/8). Meter and tempo changes are honored. Note queries use overlap; recipe start/end and timing-check use note onsets. `groups` distinguishes group UUID, reference UUID and offline group index; a shared group can appear several times at different offsets.

## Isolated-stem diagnostics

Install `sv2cli[audio]` (NumPy), or the render extra. Timing analysis accepts integer PCM16/24/32 WAV. Always select exactly one track and supply its isolated stem, preferably dry; the CLI cannot verify stem identity from the filename.

```sh
sv2cli timing-check song.svp lead.wav --track '#1' -o timing.json
sv2cli timing-check song.svp excerpt.wav --track '#1' --audio-origin 20 --search 0.5
```

By default audio zero corresponds to project zero. `--audio-origin 20` means the supplied WAV begins at project second 20. Optional `--start`/`--end` select a score region with surrounding note context retained. `--search` bounds entry search; `--tolerance` controls measurable entry deviation, in seconds. Do not widen every window just because one short syllable is absent.

The report includes per-note expected start/end, interior activity, sustained energy-entry proxy and release proxy where measurable. Connected, overlapping or already-active boundaries remain unresolved. It is not an F0/phoneme aligner, reference matcher or listening test; `alignmentVerified` and `subjectiveListeningVerified` stay false. `valid` means no activity/observable-entry failures in this diagnostic, not complete musical acceptance. Breathy consonants, noise and reverb can bias energy estimates. First/last syllables and contiguous repeated notes need explicit review.

## Explicit audio shift

```sh
sv2cli audio-shift song.svp lead.wav --track '#1' --seconds -0.24 -o corrected.wav
```

Negative advances and positive delays the whole supplied WAV. Use a currently measured offset, not a fixed singer-wide compensation. PCM16/24 is written without resampling, pitch shifting or score modification. Positive shifts pad the beginning and retain the tail. Negative shifts retain the original length with trailing zeros, and reject removal of non-silent leading samples. A shift also fails if any previously active expected note window becomes silent. Source audio and SVP cannot be overwritten by this command. Reports contain before/after diagnostics; they do not claim that all phonemes are aligned.

For independent phrase offsets, prepare temporary phrase projects with known preroll/origin and reassemble on the original timeline; rerun per-track activity checks after assembly. There is no native region-render option or automatic reference-audio time warp in this release. Avoid inferring phrase latency solely from harmonic crossings: a wrong crossing can suggest moving in the opposite direction and empty the first note.

## Direct SVP overwrite

```sh
sv2cli edit song.svp --recipe recipe.json --score-lock --in-place --dry-run
sv2cli edit song.svp --recipe recipe.json --score-lock --in-place
sv2cli mixer song.svp --gain -3 -o song.svp --force
```

`edit`, `voice`, `mixer`, `repair` allow source overwrite, with validation, timestamped byte-for-byte backup and atomic replacement. Dry-run creates no backup or file. Source bytes are rechecked before overwrite to avoid applying a stale edit over a changed file. An OS-level write/replace error leaves the previous source intact; its backup is retained. Covering an input with a query/conversion/audio/render output remains rejected.

Overwrite permission and score-edit permission are independent. For written timing corrections use `--allow-score-changes`; `--score-lock` still rejects any changed written timing. The companion [production skill](https://github.com/White-Wolf-233/sv2cli-skill) covers diagnosing timing alongside dynamics, phrasing, reference interpretation and delivery.
