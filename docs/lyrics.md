# Lyric text and syllable underlay

Available in **0.3.0.dev2+**. These core tools need no plugin, NumPy or voicebank.

```sh
sv2cli --version
sv2cli lyrics-plan-schema
sv2cli lyrics-check song.svp --plan lyrics-plan.json --require-full-project -o lyrics-audit.json
sv2cli render song.svp --lyrics-plan lyrics-plan.json --stems -o stems
```

Build the plan from independently checked score/lyric underlay. Expand each performed verse and ending separately; reusing a melody does not mean reusing its words. Do not reverse-export the same SVP as its own independent proof. The schema includes a small example with `reviewed: false`; replace it with an actual source reference and review, rather than merely changing that boolean to satisfy a gate.

The plan has `source: {reference, reviewed}` and `tracks: [{selector, phrases}]`. Selectors are exact track names or one-based `#N`. Each phrase has a unique `id`, absolute quarter-beat `start`/`end`, expected syllable text `text`, and `notes: [{at, dur, pitch, lyrics}]`; `phonemes` is optional. Decimal numbers or fraction strings are accepted for times only if exactly representable in integer blicks. Unknown fields and overlapping phrases fail.

Each performed note has a row. A new syllable is written at its actual note; subsequent notes sustaining that syllable explicitly contain `-`. Phrase text is formed by joining lyrics and omitting only `-`. No punctuation, special symbols, placeholders or repeated vowels are silently discarded. Tie chains must already be represented correctly in the source/plan; the checker does not infer ties or rewrite the score.

`lyrics-check` compares text and exact pitch/onset/duration/lyric assignments, reports the track, phrase and note differences, and resolves main/library references plus their time/pitch offsets. It catches missing, additional, wrong-order and incorrectly assigned notes even when aggregate text/counts match. Empty lyrics and orphan continuations fail; continuations crossing a gap are reported for score review. Muted, disabled and instrumental notes are counted separately from audible notes.

`--text-only` permits missing note maps for initial diagnosis. Its success does **not** establish correct syllable timing. By default the report can cover selected phrases; `--require-full-project` additionally rejects any audible project note without an exact matching map. `valid` refers only to the stated plan comparison; the report separately exposes coverage, declared source review, and unverified original-score/phoneme/listening status. Validation mismatch exits 2 and also stops an ordinary `batch` before later jobs.

`render --lyrics-plan` is optional for existing trusted projects or intentionally wordless probes. For newly entered or revised lyrics, supply it to gate synthesis: a complete, matching, declared-reviewed full-project plan is required **before** plugin loading, including when rendering selected tracks or resuming. A failed gate never retries, moves audio or starts a worker. The command result includes plan/project hashes and the audit. Save a separate `lyrics-check -o` report for the acceptance record. Matching a supplied plan cannot prove that the supplied plan itself is musically correct or that the singer pronounced it correctly.

`lyrics.set` / `phonemes.set` now require one track and sort matching notes by absolute onset across references. Simultaneous onsets fail as ambiguous. They preserve note IDs and return a reviewable `noteOrder`; they do not translate a continuous lyric string into a syllable plan. For exact local corrections, use `notes.update` with note UUID and reference selectors. Text/phoneme edits require `--allow-score-changes`; compare expected changes independently instead of claiming the entire score fingerprint remains unchanged.
