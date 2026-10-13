# Optional live API

```sh
sv2cli live install --scripts-dir /path/to/Studio/scripts --session studio
```

Rescan scripts in Studio and start the installed script once. It polls a local mailbox with `SV:setTimeout`; no network listener or arbitrary-code evaluation is exposed. Offline file commands and VST3 rendering are independent of this script.

| Method | Arguments |
|---|---|
| `host.info` | none |
| `project.summary` | none |
| `notes.list` | `track`, `group` (one-based, default 1) |
| `computed.phonemes` | track/group |
| `computed.pitch` | track/group, absolute `start` and `interval` in blicks, `frames` 1..100000 |
| `playback.status`, `.play`, `.stop`, `.pause` | none |
| `playback.seek` | `seconds` |
| `retake.generate` | track/group/note; duration/pitch/timbre booleans; `expectedProject` |
| `retake.activate` | track/group/note; take `id`; `expectedProject` |

Example:

```sh
sv2cli live call --session studio --method playback.seek --args '{"seconds":30}'
sv2cli live call --session studio --method computed.pitch --args '{"track":1,"group":1,"start":0,"interval":7056000,"frames":100}'
```

Computed data can be empty while the engine is still calculating. Lua group-reference indexing includes the main reference, so it differs from offline library-group indexing. Retake generation uses the documented `generateTake(newDuration,newPitch,newTimbre)` and adds an undo record. It affects editor memory; save the result in Studio. The API cannot save or bounce the project.

Each client session allows one pending request, validates request/response IDs and uses expiration. Use a **different session name per Studio instance**; two running bridges sharing one session are unsupported. Calls can include `expectedProject` for a file-identity guard. A timed-out mutation may already have happened, so inspect the open project before retrying. The installer backs up changed bridge scripts and identical installs are idempotent.

Live code is tested with Lua execution and mailbox/API mocks. Actual in-editor live integration is not part of the verified native-render path in this release.
