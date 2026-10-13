# Function inventory / 功能清单

Reviewed against the [SV2 user manual](https://sv2.docs.dreamtonics.com/en/interface) and [public scripting reference](https://resource.dreamtonics.com/scripting/). Run `sv2cli capabilities` for the machine-readable version. “Implemented” means a command/recipe exists; actual voice synthesis depends on the installed plugin. See [validation](validation.md) for tested environments.

| Studio area | CLI support | Route / boundary |
|---|---|---|
| Project management | Create, read, inspect, validate, repair, save copies, diff | `new`, `inspect`, `validate`, `repair`, `diff` |
| Track management | Names, colors, order, inclusion, add/remove/clone | `track.*` recipe operations |
| Groups | Query; shared-group isolation; timing/pitch offset/removal | `notes`, `group.*`, copy-on-write |
| Voice database | Switch default and overrides; explicit inheritance | `voice --name`, `voice.switch` |
| Bank discovery | Cached product metadata and installed directory IDs | `voices`; installation/activation deliberately unverified |
| Language | Group language and phoneset override; note-specific fields | `language.set`, `notes.update` |
| Pronunciation dictionary | Assign dictionary identifier to references | `dictionary.set`; editing vendor dictionary files remains external |
| Vocal modes | Preset/inheritance/per-mode values | `voice.set` with `vocalModePreset`, `vocalModeInherited`, `vocalModeParams` |
| Voice parameters | Loudness, tension, breathiness, gender, tone shift, vibrato and other saved settings | `voice --params`, `voice.set` |
| Choir | Stem count/separation and saved spread fields | `voice.set`; explicit per-note attributes |
| Notes | Query, filter, replace, update, transpose and shift | `notes`, `notes.*` recipes |
| Lyrics and phonemes | Query and exact-count batch assignment | `lyrics.set`, `phonemes.set`, CSV/JSON |
| Singing/rap/spoken mode | Saved note mode/accent/attributes | `notes.update`; caller supplies SV2-valid values |
| Detailed note expression | Saved note attributes, detune, language | `notes.update`; unknown attribute payloads preserved |
| Retakes | Activate existing takes offline; generate via live API | `retake.activate`, `live call` |
| Automation | Native flat SVP points; recipe accepts paired points | `automation.set`; local group coordinates in blicks |
| Pitch controls | Read through raw SVP and replace controls | `pitch.controls`; curve payload follows installed SVP schema |
| Computed phonemes/attributes/pitch | Live engine data | Optional Lua bridge; can return empty data while calculating |
| Tempo, time signatures | Edit maps; convert musical time to seconds | `tempo.set`, `meter.set`, `time` |
| Playback | Status, play, stop, pause, seek | Optional Lua bridge; seconds for seek |
| Mixer | Gain, pan, mute, solo | `mixer`, `mixer.set` |
| Room/EQ/compression/reverb | Update saved effect payloads | `effects.set` |
| Instrumental audio tracks | Existing unknown fields preserved | No high-level importer; use Studio import or guarded JSON Patch with known schema |
| MIDI | Import/export with lyrics, tempo and meters | `convert midi-in/out`; unsupported/lossy timing is rejected |
| Notes CSV/JSON | Export/import numeric notes | `notes`, `convert csv-in/out`; replacing notes is an explicit score edit |
| MusicXML | Native Studio import | Host-only; no silently lossy reimplementation in this release |
| Audio render | Master stereo bus; selected tracks; numbered stems | Installed instrument VST3; PCM16/24, 1/2 channels |
| Native aspiration / pitch export | Not exposed by main VST3 audio bus | Host-only; saved render configuration can be prepared with `render.configure` |
| Full ARA | DAW integration | Host-only; do not pass the ARA plugin to this renderer |
| Voice-to-MIDI | Vendor inference | Host-only |
| Product manager | Purchase, activation, trials, downloads | Host-only; no license files inspected |
| Keyboard/UI appearance | Studio preferences | Outside project automation scope |
| Version-specific SVP fields | RFC 6902 guarded patch | `json.patch`; validation and score lock still apply |
| Environments/batch | Profiles, environment overrides, argv jobs | `config`, `doctor`, `batch`; command backend has no shell |

The CLI covers project data rather than emulating every screen interaction. Saved payload operations do not guarantee that a particular installed bank supports the requested Vocal Mode, language or unusual note attribute.
