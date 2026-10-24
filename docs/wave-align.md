# Waveform entry alignment

`wave-align` is an explicit post-render operation for a dry, isolated vocal
stem. A loaded score, a nonempty WAV and converged rendering passes do not
establish sample timing. In the motivating real render, common written entries
had different waveform energy delays on S, A and T, despite the plugin reporting
zero latency. No fixed singer-wide latency is assumed.

## Render acceptance

Native `render` now defaults to `--entry-policy check`: after readiness and
format checks, it measures the first actual isolated waveform attack. An
unresolved attack or error larger than `--entry-tolerance 0.03` seconds fails
before the requested WAV is written. `entry-timing.json` remains in the job
directory, including observed later phrase entries. A multi-track mix cannot
establish individual entries: use `--stems`, or explicitly choose report-only.

```
sv2cli render song.svp --stems -o checked-stems
sv2cli render dry.svp -o aligned.wav --entry-policy align
sv2cli render song.svp -o unchecked-mix.wav --entry-policy report
```

`align` explicitly opts into a measured whole-recording translation. Use it for
a reviewed recording offset; waveform energy can also reflect intended breath,
consonant and attack shaping. Raw native audio is retained in the job directory.
No automatic phrase warping is performed. The final manifest separately records
`firstWaveformEntryVerified`, `allNoteOnsetsVerified` and the per-output evidence;
success at the first landmark never certifies all notes or phonemes. The entry
policy and tolerance are part of the resume fingerprint. The command backend
defaults to report-only/unchecked to preserve its dependency-free contract;
explicit check/align also works there with the `audio` extra installed.

The native short-project reproduction used the same six opening notes at
76 BPM, 48 kHz and a 512-sample buffer. Four repeated passes of the same S part
produced 12%-RMS landmarks at 9.610 s, 9.620 s, and two unresolved entries outside
the search interval; the score entry was 9.473684 s. A second message-pump
schedule produced landmarks at 9.758, 9.502, 9.684 and 9.930 s. The plugin
reported zero latency throughout. This establishes render-path timing drift
and the previous acceptance gap; it does not localize the proprietary engine's
internal cause or prove a score-time calculation bug. Increasing pump frequency
alone did not solve it. The guard and explicit correction address acceptance
and the measured recording offset, rather than changing the engine binary.

The new acceptance path was also exercised with the real native worker. A
diagnostic `--single-pass` job with a +284 ms entry failed with
`entry_timing_mismatch`, preserving the raw WAV and writing no final WAV. A
separate normal (convergence-required) `--entry-policy align` job stabilized
after six passes but still had a +264.316 ms first landmark. Its measured
264.3125 ms PCM translation yielded a -1.684 ms landmark error at 48 kHz,
stereo PCM24. No score or resampling changes were involved. These are short
opening-project results, not full-song or independent listening certification.

```
sv2cli wave-align song.svp dry.wav --track '#1' -o aligned.wav
```

The default `--scope track` measures the first attack at 2 ms RMS resolution and
translates the whole recording by that measured amount. This preserves every
sample interval and is appropriate after confirming a consistent recording
offset across the song. The companion `.alignment.json` retains observed later
entries, including unresolved entries; it does not label them all aligned.

`--scope phrase` independently measures phrases separated by `--gap` seconds
(default 0.35). It refuses unresolved attacks and refuses to splice audible
tails. Use this only for separate phrase delays confirmed by inspection, rather
than normal consonant or melodic phrasing differences.

Both modes preserve duration, pitch, sample rate and the source SVP. Audio and
project sources cannot be overwritten. Advancing cannot discard active leading
samples; delaying cannot discard an active tail. Previously active note
interiors cannot become silent. Numeric parameters and the presence of exactly
one isolated track are validated. PCM16/24 outputs retain the input format.

The anchors are waveform energy, not phoneme boundaries. Successful selected
entry correction is reported separately from all-note timing and listening.
Tests use independently delayed carrier recordings with distinct phrase delays,
and include unsafe crop, silent input and active-boundary rejection.
