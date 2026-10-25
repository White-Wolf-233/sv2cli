# sv2cli

[简体中文](README.zh-CN.md) · [Feature inventory](docs/features.md) · [Recipes](docs/recipes.md) · [Rendering](docs/rendering.md)

A reusable CLI for **Synthesizer V Studio 2** projects: inspect and repair SVP files, switch singers without leaving stale group overrides, edit voice/mixer/tuning parameters, batch jobs, and render through the installed VST3 instrument plugin.

For agent-assisted production, use the separate [sv2cli-production skill](https://github.com/White-Wolf-233/sv2cli-skill). It covers measured timing, dynamics, score protection, overwrite choices and delivery.

Project tools are dependency-free and work on Windows, macOS, and Linux. Native
rendering uses a separately built direct VST3 host and its message loop. A
licensed plugin and activated voice are required. No screenshot recognition,
mouse coordinates or keyboard automation is used.

```sh
git clone https://github.com/White-Wolf-233/sv2cli.git
cd sv2cli
python -m pip install ".[render,midi]"
sv2cli doctor
sv2cli inspect song.svp
sv2cli validate song.svp
# Build native/ and set SV2CLI_NATIVE_HOST first; see native/README.md.
sv2cli render song.svp --stems -o stems --warmup 30 --timeout 1800
```

Python 3.10+ is required for the core. The native library uses a versioned C ABI
instead of a Python-version-specific host wheel. **Windows 11 / Python 3.12 /
SV2 2.2.1 / Teto AI 2** is locally tested. macOS needs independent native plugin
validation. Linux supports core tools and the command backend.

## Common jobs

For new or corrected lyrics, use `sv2cli lyrics-plan-schema`, then `lyrics-check --plan ... --require-full-project`. `render --lyrics-plan ...` rejects incomplete or mismatched underlay before loading the plugin. This checks independent phrase text and exact syllable-to-note assignment, rather than treating note counts, F0 or nonempty audio as proof of correct words. See [lyrics and syllables](docs/lyrics.md). Available in 0.3.0.dev2+.

Switch all selected track/group references to a different SV2 singer:

```sh
sv2cli voice song.svp --track "#1" --name "Kasane Teto AI 2" -o song-teto.svp
sv2cli voice song-teto.svp --track "#1" --language-override mandarin -o song-zh.svp
sv2cli voice song-zh.svp --track "#1" --params @examples/male-voice.json -o song-male.svp
sv2cli mixer song-male.svp --track "#1" --gain -3 --pan 0.2 -o song-balanced.svp
sv2cli diff song.svp song-balanced.svp --summary
```

`--track` accepts an exact name or a one-based `#N`; repeat it to select multiple tracks. Omitting it selects all tracks. Voice identities are exact names, not fuzzy matches. If your bank uses another database version/language/phoneset, supply `--database-version`, `--language`, `--phoneset` and `--backend`; defaults are SV2 Japanese/SVR3/201/romaji. A successful file edit is not proof that the selected singer is installed or activated. Cached catalog entries (`sv2cli voices`) are labeled accordingly.

Switching singers preserves existing cross-language pronunciation overrides. Mandarin language override also sets the matching `xsampa` phoneset; Japanese uses `romaji`. `--override-phoneset` explicitly selects the override encoding for other language/bank combinations. Lyrics and explicit phonemes stay unchanged.

Existing outputs fail unless `--force` is supplied. `edit`, `voice`, `mixer` and `repair` also support **`--in-place`**, or `-o INPUT.svp --force`, to atomically overwrite the source SVP after saving a timestamped backup. Score-lock and validation still apply. Query/conversion/render outputs cannot replace their inputs. Unknown native JSON fields are preserved; unknown recipe operation fields are rejected.

```sh
sv2cli mixer song.svp --track "#1" --gain -3 --in-place --dry-run
sv2cli mixer song.svp --track "#1" --gain -3 --in-place
sv2cli time song.svp --at bar:53:1
sv2cli groups song.svp --track "#1"
sv2cli timing-check song.svp lead.wav --track "#1" -o timing.json
sv2cli audio-shift song.svp lead.wav --track "#1" --seconds -0.24 -o lead-aligned.wav
sv2cli job-status stems
```

The last command applies an explicitly measured offset; negative advances audio, positive delays it. Timing checks use activity/energy proxies on an **isolated stem**, report unresolved legato boundaries, and never claim phoneme alignment. Unsafe leading crops and lost previously active note windows are rejected. See [timing and overwrite workflows](docs/timing.md). Timing tools need the `audio` extra (NumPy), also supplied by `render`.

Apply a recipe atomically and enforce score identity:

```sh
sv2cli edit song.svp --recipe examples/choral-mix.json --score-lock -o choir.svp
sv2cli edit song.svp --recipe examples/choral-mix.json --dry-run -o preview.svp
```

Score-changing operations require `--allow-score-changes`; `--score-lock` still rejects changes to pitches, timing, lyrics, phonemes, tempo, meter or track arrangement. The lock concerns the written score. Voice/tuning curves can change the performed sound.

```sh
sv2cli notes song.svp --track "#1" -o notes.json
sv2cli convert midi-out song.svp -o song.mid
sv2cli convert midi-in song.mid -o imported.svp
sv2cli render song.svp --stems -o stems --channels 2 --bit-depth 24
sv2cli audio-check mix.wav --expected-seconds 120
sv2cli batch examples/batch.json
sv2cli capabilities
```

Native renders use the [direct single-pass VST3 host](native/README.md), isolated
workers, PCM16/24 and timeout/cancellation. It processes audio and plugin messages
on the owning thread with an integer sample clock. Loaded score identity,
activity, format and clipping are checked. A failed render is rejected; automatic
retries and energy-envelope convergence loops are disabled. Each output has a
JSON manifest and retained job evidence. Stems use numbered filenames mapped
back to their original track names.

Native rendering also checks the **first actual isolated waveform entry** by
default (30 ms tolerance). Multi-track jobs should use `--stems`; explicitly
unchecked mixes need `--entry-policy report`. For a reviewed whole-recording
offset, `--entry-policy align` measures and translates PCM without changing the
score. Existing WAVs can use `wave-align`. Reports retain unresolved later
entries and never certify all-note/phoneme alignment. See [waveform entry
acceptance and correction](docs/wave-align.md).

## Environments and live API

Named JSON profiles separate machine paths and custom render adapters:

```sh
sv2cli config set --name studio --value @examples/profile.json
sv2cli --profile studio doctor
sv2cli --profile studio render song.svp -o mix.wav
```

`SV2CLI_CONFIG`, `SV2CLI_PLUGIN` and `SV2CLI_MAILBOX` override configuration locations. A command backend runs an argv array without a shell; see [environment configuration](docs/environments.md).

Offline commands and VST3 rendering need no Studio script running. For the currently open editor's computed phonemes/pitch, playback and Retake generation, install the optional official-API Lua bridge:

```sh
sv2cli live install --session studio
# In Studio: Scripts > Rescan, then start the installed sv2cli bridge once.
sv2cli live call --session studio --method host.info
sv2cli live call --session studio --method notes.list --args '{"track":1,"group":1}'
```

The bridge is local and session-scoped. Start different instances with different session names. Retake writes require `expectedProject` to match the active project's path; they change editor memory and are not automatically saved. Timed-out writes are not safe to retry blindly. See [live API](docs/live.md).

## Support boundaries

[The full inventory](docs/features.md) lists implemented commands and host-only features. Dreamtonics' public scripting API does not expose native project save or audio bounce. The VST3 backend therefore uses the **public plugin-state interface** to pass project JSON and the main audio bus to retrieve audio; it does not patch the proprietary engine. Plugin compatibility is version-dependent and unknown state layouts are rejected.

Product activation/downloads, Full ARA, native isolated-aspiration export, voice-to-MIDI inference and MusicXML import remain in Studio. The CLI does not pretend these are available as public API calls.

## Development

```sh
python -m pip install ".[dev,midi]" numpy lupa
python -m pytest -q
python -m build
```

CI checks the project tools on Windows/macOS/Linux and Python 3.10/3.12/3.13. Licensed plugin tests are separate from those checks. [Validation details](docs/validation.md) distinguish real synthesis, transport mocks and subjective listening.

The CLI code is MIT-licensed; bundled `rxi/json.lua` keeps its MIT license. Optional audio-host dependencies and installed Dreamtonics products retain their own licenses. No engine binaries, voice databases, license files or copyrighted song projects are distributed.

## Production feedback update

Development version 0.3.0.dev1 adds monophonic vocal preflight, explicit MIDI overlap/polyphony policies, all-note coverage and score-aware silence checks, SV2 rigid/flat pitch control, sample-peak normalization and effect schemas. See [commands, evidence and boundaries](docs/feedback-fixes.md). Verify the actual package path with `doctor` when multiple installations exist.
