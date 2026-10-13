# Environment profiles

Core commands require only Python 3.10+. MIDI needs `sv2cli[midi]`; native rendering needs `sv2cli[render]`, the VST3 instrument, an available desktop and an activated singer. Dreamtonics SV2 has Windows/macOS installations; a native Linux render path is not claimed.

Config location:

| OS | Path |
|---|---|
| Windows | `%APPDATA%/sv2cli/config.json` |
| macOS | `~/Library/Application Support/sv2cli/config.json` |
| Linux | `$XDG_CONFIG_HOME/sv2cli/config.json` or `~/.config/sv2cli/config.json` |

Set `SV2CLI_CONFIG` to use another file. `SV2CLI_PLUGIN` overrides the resolved plugin path. `SV2CLI_MAILBOX` sets the live bridge mailbox root. The default profile discovers standard VST3 and Dreamtonics data paths; custom named profiles must exist explicitly.

```json
{"profiles":{
  "studio":{"plugin":"/Library/Audio/Plug-Ins/VST3/Synthesizer V Studio 2 Plugin.vst3"},
  "adapter":{"render_command":["my-render-adapter","--svp","{project}","--wav","{output}","--seconds","{duration}"]}
}}
```

```sh
sv2cli --profile adapter render song.svp -o output.wav --backend command
```

`render_command` is an argument array passed directly to `subprocess`, never to a shell. Placeholders are `{project}`, `{output}`, `{duration}` and `{job}`. The adapter must write the requested WAV, return only after completion and exit nonzero on failure. The CLI independently validates its output. `{job}` points to a JSON file with format/length settings. Use a wrapper executable for remote/WSL/container adapters; there is no automatic path translation or claim that licenses travel across environments.

JSON output is emitted to stdout. Progress/errors go to stderr; worker logs retain native messages. Exit status 0 = success, 2 = validation/operation error, 130 = cancellation. `doctor` detects prerequisites but does not claim a render succeeded.
