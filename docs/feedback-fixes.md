# Production feedback fixes (0.3.0.dev1)

This revision addresses the eight findings in the 2026-10-25 Winter test report.
The report used the old 0.1.0 editable installation. Check `--version` and
`doctor`: the latter now prints the exact Python executable, package directory
and native host. A source checkout does not silently upgrade another installation.

## MIDI input and vocal preflight

```sh
sv2cli convert midi-in score.mid --polyphony split --lyric-default a -o voices.svp
sv2cli convert midi-in performance.mid --truncate-overlaps --polyphony split -o voices.svp
sv2cli preflight voices.svp -o preflight.json
```

Default import preserves polyphony and reports a warning. `--polyphony reject`
(`--monophonic`) rejects it. `--polyphony split` partitions overlapping notes
into independent vocal tracks without changing their pitches, starts or lengths.
Different MIDI channels are imported separately. This is interval partitioning,
not a claim to recover a composer's SATB voice assignment.

`--top-voice` (`--polyphony top`) explicitly selects the highest currently sounding
pitch. It can discard, shorten or divide lower notes. `--truncate-overlaps` is
also explicit: an earlier same-pitch note ends at the next attack. MIDI note-offs
are paired FIFO; genuinely ambiguous overlapping same-pitch performances cannot
be recovered losslessly. The conversion result reports truncation locations and
discarded zero-length notes. Pedal controllers are not expanded into vocal note
durations. `--midi-charset latin1` supports non-UTF8 MIDI text.

Without a MIDI lyric event, the default is **la**. `--lyric-default` changes only
that default. Simultaneous note/lyric event ordering is retained on export.

`validate` checks structural SVP validity, including meter maps and known SV2
expression bounds. `preflight` additionally checks audible vocal intervals,
including overlaps across different group references in the same track. Vocal
rendering rejects overlap before launching a backend and reports track, pitches,
note/reference IDs, blick positions and seconds. It never silently drops notes.

## Single pass and audio completeness

`--attempts` still only accepts **1**. There is no convergence loop, automatic
render retry, or fallback to DawDreamer. Warmup is stopped and produces no audio.
Increasing attempts is not the resolution of an incomplete render.

All positive-duration notes now receive a central 60% activity window; notes
at or below 250 ms are no longer dropped. Windows outside the WAV fail.
Additionally, 10 ms RMS blocks are checked inside the union of expected score
activity. A default continuous 0.5 s below -80 dBFS fails with `incomplete_audio`.
Written rests, lead-ins and tails do not count as unexpected silence.

```sh
sv2cli coverage-check song.svp isolated.wav --track '#1' -o coverage.json
sv2cli render song.svp --stems -o stems --silence-dbfs -80 --max-silent-seconds .5
```

The silence settings are explicit configuration, not an automatically adjusted
acceptance target. Coverage remains energy evidence: other voices, noise or
reverb can mask individual missing notes in mixed audio. Use isolated stems.
The standalone check can inspect retained failed audio without another render.
The native backend enforces it automatically; the custom command backend does
not claim native coverage/readback verification.

Worker error codes and the coverage-log path survive to the top-level manifest.
CLI version and acceptance revision participate in resume fingerprints, so old
weakly checked outputs cannot be reused under the new acceptance contract.
All newly rendered stems share the original project's full timeline and length.

## SV2 expression and slide control

```sh
sv2cli tune song.svp --mode rigid --vibrato 0 -o rigid.svp
sv2cli tune song.svp --mode flat --transition-ms 5 --vibrato 0 -o flat.svp
sv2cli tune flat.svp --mode flat --transition-ms 10 --replace-controls -o revised.svp
```

`rigid` writes SV2's `expValueX=0, expValueY=0`; optional `--vibrato` writes
`dF0VbrMod` (supported CLI range 0–2). `flat` additionally generates native
PitchControlCurve objects at the existing note pitches, including detune, and
limits each transition around its existing note boundary. `--transition-ms`
accepts 0–500; widths are bounded by the neighboring notes. Zero is represented
by a one-blick step. No onset, duration, lyric, phoneme, tempo or note pitch is
changed. The requested width is a control-curve width, not a guarantee about an
acoustic transition duration below the analysis/engine resolution.

`--track`, `--start`, `--end` select notes. Existing control curves or pitch
deviation edits are not silently overwritten: explicit `--replace-controls`
requires selecting the entire affected group. `--mode default` restores default
expression only, retaining any explicit pitch curves. It is not a pitch reset.

Recipe equivalents are `notes.expression` with `preset`/optional `vibrato` and
`pitch.flatten` with optional `transitionMs`/`replaceControls`, plus standard note
filters. Native `pitch.controls` payloads now receive structural validation.
The plugin's loaded state is checked for explicitly requested expression,
control-curve values and effects, tolerating float serialization and regenerated
control IDs. Silent ignoring or clamping fails before playback.

Pitch sliding and vowel rearticulation are separate. If explicitly requested,
`notes.articulate` with `gapMs` shortens durations and therefore requires
`--allow-score-changes`. It is never the default slide-control method:

```json
[{"op":"notes.articulate","tracks":["#1"],"gapMs":10}]
```

SV1's old tF0Left/tF0Right/manual-mode controls are not the SV2 implementation.
See [Dreamtonics' SV2 migration guidance](https://dreamtonics.zendesk.com/hc/en-us/articles/49917044644505-Alternative-approaches-to-Manual-Mode)
and [public note API](https://resource.dreamtonics.com/scripting/Note.html).

## Level and effect controls

```sh
sv2cli render song.svp --track '#1' --target-peak -1 -o lead.wav
sv2cli audio-normalize raw.wav --target-peak -1 -o normalized.wav
sv2cli effects song.svp --params @effects.json -o effects.svp
sv2cli recipe-schema
```

`--normalize` is an alias for `--target-peak -1`. Supported targets are -60 to
-0.1 dBFS. This is constant sample-peak gain on PCM16/24, with identical frame
count, rate, channels and sample positions. It is not limiting, true-peak or LUFS
normalization. On `--stems`, each file is normalized independently; that changes
relative voice balance. For preserving a mix's balance, normalize its mixdown.
Raw audio and applied gain remain in the job evidence. Audio reports now include
`peakDBFS` and `rmsDBFS`; silence is JSON null, never nonstandard Infinity.

`recipe-schema.effects.fields` lists supported effect fields, units and numeric
constraints. Nested typos, nonfinite values, wrong booleans and invalid ratios
fail early. The tested reverb type is `clean`; no other enum is guessed. Not all
vendor bounds are documented: unspecified bounds mean finite values, not a claim
that every value is accepted by the engine. Plugin readback rejects clamping.
Other vendor extensions remain available through an explicit, justified JSON
Patch. See `examples/choral-mix.json` for a complete supported reverb payload.

## Evidence and boundaries

Local Windows SV2 2.2.1 / Teto AI 2 validation used one pass per distinct input:
an eight-note default vowel probe, the score-identical flat/5 ms probe, and a
24-note 85 ms flat probe with reverb and normalization. Readback retained the
expression and curves. The eight-note comparison's central-half F0 analysis
measured median absolute error 13.32 → 1.03 cents, and frames within 50 cents
93.21% → 100%. These are bounded autocorrelation estimates, not human listening
or all-phoneme certification. `scripts/probe_pitch.py` reproduces analysis on
retained WAVs and does not invoke rendering.

On the retained Winter 1976-note audio, the new check measured 526 missing core
windows and a 23.68 s unexpected silent span that the old check omitted. Original
3729-note MIDI imported with one explicit same-onset truncation/zero-length
discard into eight monophonic tracks; the prepared 3728-note MIDI split into seven
tracks without truncation. Source files were not overwritten.

Still outside this CLI's supported public interface: native region rendering,
Full ARA, activation/downloads, isolated aspiration export, native voice-to-MIDI
and full-fidelity MusicXML import. This change does not claim to implement every
Studio GUI feature or automatically reconstruct score voice assignments.
