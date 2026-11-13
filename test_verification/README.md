# CLI feature verification

Result: all 18 fixture and supported-command checks passed. Two requested command spellings are unsupported; see the captured stderr files and verification-report.json. The source implementation was not changed.

Fixtures:
- helloworld.svp: one track, 120 BPM, 4/4, exactly 16 quarter beats (four bars). MIDI pitches 60, 62, 64, 65, 67. Lyrics are 你 / 好 / 世 / 界 / +; the last note continues 界. Quarter-beat durations are 2, 2, 4, 4, 4.
- test.wav: NumPy sine generated with scipy.io.wavfile.write; 440 Hz, two seconds, stereo, 44100 Hz, PCM16, 0.75 peak amplitude per channel. Readback confirmed format, dominant frequency, and identical channels.

Verified commands (from the repository root):

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\test_verification\_deps"
python -m sv2cli full-score-text test_verification/helloworld.svp -o test_verification/full-score-output.json --force
python -m sv2cli loudness-check test_verification/test.wav
python -m sv2cli audio-check --lufs test_verification/test.wav
```

The score command writes the actual score JSON to -o. Its stdout is a small receipt, saved separately as full-score-stdout.json. The two audio commands' raw stdout is saved as loudness-output.json and audio-check-lufs-output.json.

Measured integratedLUFS: -3.2 in both audio commands. Estimated truePeakDBFS: -2.5. shortTermBins contains a value. Intervals are null for the first note, then +2/M2, +2/M2, +1/m2, +2/M2.

Requested syntax failures (exit 2):
- python -m sv2cli inspect full-score-text test_verification/helloworld.svp
- python -m sv2cli audio-check loudness-check test_verification/test.wav

These are top-level commands, not subcommands of inspect/audio-check. Raw failure stdout and stderr are in requested-*.txt. All commands, return codes, checks, source hashes and environment information are in verification-report.json.

Run the complete verification again:

```powershell
python test_verification/verify_features.py
```

The script explicitly imports this checkout rather than the global sv2cli installation. NumPy 2.2.6 was installed only into the ignored _deps directory; the existing SciPy installation was reused. test.wav is ignored by the repository's existing WAV rule but is present on disk.

LUFS depends on signal amplitude and channel count. The two-second clip uses the implementation's shortened short-term window, not a full three-second window. True peak is the implementation's linear-interpolation estimate. This smoke test does not certify BS.1770 compliance. No Synthesizer V application, plugin or voice library was installed or loaded.

The ancillary doctor command returned exit 2 because the sandbox denied access to the protected Dreamtonics app-data directory. Its raw stdout/stderr are preserved separately. The offline score and audio checks all succeeded.
