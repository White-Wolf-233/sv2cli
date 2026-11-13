# CLI feature verification

Run the offline fixture and command checks from the repository root.

```sh
python test_verification/verify_features.py
```

The script imports this checkout and saves command output, return codes and
18 checks in `verification-report.json`.

- `helloworld.svp` contains five notes at 120 BPM in 4/4, spanning four bars.
  Lyrics are 你 / 好 / 世 / 界 / -. The final hyphen sustains 界.
- `test.wav` is a two-second stereo 440 Hz sine at 44100 Hz, PCM16, with
  0.75 peak amplitude per channel.

```sh
sv2cli full-score-text test_verification/helloworld.svp -o score.json
sv2cli loudness-check test_verification/test.wav
sv2cli audio-check test_verification/test.wav --lufs
```

`full-score-text` writes the score JSON to `-o` and prints a receipt.
`loudness-check` reports integrated LUFS, short-term bins and a 4x FIR
true-peak estimate. The two-second fixture uses a shortened short-term window.
