# Transactional edit recipes

```sh
sv2cli edit input.svp --recipe recipe.json -o output.svp --score-lock
```

A recipe is an array of objects. Each uses `op` and usually `tracks` (exact names or one-based `#N`). Omit `tracks` for all tracks. Unknown operations fail. The entire recipe runs on a copy; validation occurs before saving. Shared library groups are copied when editing only some of their users.

Score-changing operations need `--allow-score-changes`. `--score-lock` always takes precedence and compares note pitches/timing/text/type/mute, tempo, meter and track arrangement. Raw JSON Patch cannot bypass it.

| Operation | Required / optional fields |
|---|---|
| `voice.switch` | `database` (name, backendType, language, phoneset, version); `inherit`, `clearDictionary` |
| `voice.set` | `values`; `scope` = all/main |
| `language.set` | `language`; optional `phoneset` |
| `dictionary.set` | `dictionary` |
| `mixer.set` | `values`: gainDecibel/pan/mute/solo/display |
| `effects.set` | `values`: room/postRoomEq/compressor/reverb objects |
| `track.rename` | one selected track; `name` |
| `track.set` | `values`: dispColor/dispOrder/renderEnabled |
| `track.add` | `name` |
| `track.remove` | explicit `tracks` |
| `track.clone` | one selected track; optional `name` |
| `notes.replace` | one track; `notes`: onset/duration/pitch/lyrics/phonemes |
| `notes.update` | `values`; optional `uuids`, `groups`, `start`, `end` |
| `notes.transpose` | `semitones`; same filters |
| `notes.shift` | `blick`; same filters |
| `lyrics.set` / `phonemes.set` | `values` array of exactly the selected note count |
| `group.shift` / `group.transpose` | `blick` / `semitones`; optional `groups` names or UUIDs |
| `group.remove` | explicit `groups` |
| `automation.set` | `parameter`, `points`: `[[blick,value],...]`; optional `groups`, `mode` |
| `pitch.controls` | `controls` array in native SVP format; optional `groups` |
| `retake.activate` | existing `id`; optional note `uuids`, `groups` |
| `tempo.set` | `marks`: `[{position,bpm},...]`, starting at position 0 |
| `meter.set` | `marks`: `[{index,numerator,denominator},...]`, starting at bar index 0 |
| `render.configure` | `values` native renderConfig fields |
| `json.patch` | `patch` RFC6902 array; add/remove/replace/copy/move/test |

Timing is integer **blicks**, with `705600000` per quarter. Note onsets in `notes.replace` are absolute; `notes.update` values and automation points are group-local. Filtering by `start`/`end` uses absolute note onset. `notes` query uses interval overlap. Group index 0 in offline note rows represents the main group; library references follow it. The live API uses Studio's one-based reference indexing instead.

`paramToneShift` is in cents (SV2 voice parameter), not MIDI transposition. `paramGender`, `paramTension`, `paramBreathiness` have range -1..1. Voice fields not recognized by the high-level editor can be set through a guarded `json.patch`; field support remains version-specific.

JSON Patch example:

```json
[
  {"op":"json.patch","patch":[
    {"op":"test","path":"/version","value":196},
    {"op":"replace","path":"/tracks/0/mainRef/voice/vocalModeInherited","value":false},
    {"op":"add","path":"/tracks/0/mainRef/voice/vocalModePreset","value":""}
  ]}
]
```

Use a `test` before version-sensitive edits. A recipe that would produce invalid note timing, out-of-range pitches, broken group references or invalid automation is rejected. Native field payloads that are not structurally understood are preserved, not silently normalized.
