# Direct single-pass VST3 transport

This small host replaces the DawDreamer graph-rendering path. It loads the
licensed Synthesizer V instrument through public VST3/JUCE interfaces, holds an
integer sample clock, processes one buffer on the owning message thread, then
dispatches messages before advancing the clock. Tempo and meter changes split
buffers at their nearest sample. It records the first stereo bus directly.

Warmup dispatches messages while the transport is stopped. One transport pass
produces the raw WAV, followed by coverage and format checks and an entry-timing
report. `--entry-policy check` enforces a requested timing tolerance.

## Build

Use CMake 3.22+, a supported C++17 compiler and platform SDK. Windows needs MSVC
and the Windows SDK; MinGW is not supported by JUCE 8. No global environment
configuration is needed when building from a developer terminal.

```sh
cmake -S native -B native/build -DCMAKE_BUILD_TYPE=Release
cmake --build native/build --config Release
```

The dependency is pinned to JUCE 8.0.6, commit
`51a8a6d7aeae7326956d747737ccf1575e61e209`. Pass
`-DSV2CLI_JUCE_DIR=/absolute/path/to/JUCE` to use an existing checkout.
Set `SV2CLI_NATIVE_HOST` (process/session environment) or the profile's
`native_host` to the resulting `sv2cli_transport.dll` on Windows, or
`libsv2cli_transport.dylib` on macOS. The CLI never loads the plugin/library in
its parent process: the disposable worker owns both, so cancellation also
terminates the hosted plugin's threads.

The library deliberately has a small versioned C ABI. Python validates and
patches a snapshot of the public project state, verifies loaded score identity,
and then accepts exactly one native pass. A missing library produces a clear
error; the old drifting graph host is not a fallback. Arbitrary tempo positions
are supported to sample resolution. Nonzero SVP `startTimeSeconds` is currently
rejected instead of applying an unverified offset.

## Validation scope

Windows 11 / Python 3.12 / SynthV 2.2.1 / Teto AI 2 was tested locally. Separate
S and A opening projects each produced the same 9.482 s first RMS entry in four
fixed test passes, compared with the written 9.473684 s entry. These files were
not shifted. Both new-host asynchronous and message-thread controls were stable;
restoring the old system-time/record/reset context fields also remained stable.
Thus the problem is localized to the old DawDreamer hosting path, not to a
proven specific context flag or a proven intrinsic singer latency. The exact
dependency-internal faulty operation is not yet isolated.

All seven real vocal stems were also rendered once in separate CLI workers.
For the fricative-led A2/B2 entries, retained raw PCM was spectrally inspected
and checked using the explicit voiced-energy landmark; it was not rerendered or
shifted. A separate zero-origin, off-960-grid tempo/changing-meter probe passed
as 44.1 kHz mono PCM16. The normal full stems were 48 kHz stereo PCM24.

Fixed-count repetition is used only to test reproducibility: every result is
retained. Production exports always use one pass. First waveform entry evidence
does not certify every phoneme, the written score or subjective listening.
macOS requires independent native validation.

## License

The native host and its JUCE-linked build are **AGPL-3.0-or-later**; see
[LICENSE](LICENSE). The Python CLI retains its existing MIT license. JUCE is
fetched as source; no proprietary plugin, voice, activation data or engine
binary is distributed with this code.
