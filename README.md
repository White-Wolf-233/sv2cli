# sv2cli

[简体中文](README.zh-CN.md) · [Feature inventory](docs/features.md) · [Recipes](docs/recipes.md) · [Rendering](docs/rendering.md)

A reusable CLI for **Synthesizer V Studio 2** projects: inspect and repair SVP files, switch singers without leaving stale group overrides, edit voice/mixer/tuning parameters, batch jobs, and render through the installed VST3 instrument plugin.

Project tools are dependency-free and work on Windows, macOS, and Linux. The native rendering backend uses a DAW host and an application event loop—**no screenshot recognition, mouse coordinates, or keyboard automation**. A licensed editor/plugin and activated voice are still required to synthesize audio.

```sh
git clone https://github.com/White-Wolf-233/sv2cli.git
cd sv2cli
python -m pip install ".[render,midi]"
sv2cli doctor
sv2cli inspect song.svp
sv2cli validate song.svp
sv2cli render song.svp -o mix.wav --warmup 30 --timeout 1800
```

Python 3.10+ is required for the core. Native render extras also need a Python/OS combination for which DawDreamer publishes a wheel. **Windows 11 / Python 3.12 / SV2 2.2.1 / Teto AI 2** is the locally tested render configuration; macOS rendering is implemented but needs independent plugin validation. Linux supports project tools and a configurable command backend, not a native Dreamtonics SV2 installation.

## Common jobs

Switch all selected track/group references to a different SV2 singer:

```sh
sv2cli voice song.svp --track "#1" --name "Kasane Teto AI 2" -o song-teto.svp
sv2cli voice song-teto.svp --track "#1" --language-override mandarin -o song-zh.svp
sv2cli voice song-zh.svp --track "#1" --params @examples/male-voice.json -o song-male.svp
sv2cli mixer song-male.svp --track "#1" --gain -3 --pan 0.2 -o song-balanced.svp
sv2cli diff song.svp song-balanced.svp --summary
```

`--track` accepts an exact name or a one-based `#N`; repeat it to select multiple tracks. Omitting it selects all tracks. Voice identities are exact names, not fuzzy matches. If your bank uses another database version/language/phoneset, supply `--database-version`, `--language`, `--phoneset` and `--backend`; defaults are SV2 Japanese/SVR3/201/romaji. A successful file edit is not proof that the selected singer is installed or activated. Cached catalog entries (`sv2cli voices`) are labeled accordingly.

Every write needs a new output filename. Existing outputs fail unless `--force` is supplied, and source SVP files cannot be overwritten even with `--force`. Unknown JSON fields are preserved.

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

Native renders use isolated workers, PCM16/24, timeout/cancellation, expected-note activity checks and energy-envelope convergence. The plugin's loaded score is read back and verified before rendering. Silence, empty WAVs, incomplete duration, missing activity, invalid plugin state or excessive clipping fail instead of becoming a successful result. Each output has a JSON manifest; worker logs and intermediate files remain in `.sv2cli-jobs` for diagnosis. Stem filenames are numbered (`01.wav`), with original track names in the manifest.

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
