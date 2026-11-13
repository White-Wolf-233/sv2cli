"""Reproducible verification against this checkout; no Synthesizer V required."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import wave

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
paths = [str(ROOT / 'src'), str(OUT / '_deps')]
sys.path[:0] = paths
os.environ['PYTHONPATH'] = os.pathsep.join(paths)
import numpy as np
import scipy
from scipy.io import wavfile
import sv2cli
from sv2cli.edit import apply
from sv2cli.project import Project, QUARTER, new_project


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


commands = []
def run(args, name):
    result = subprocess.run([sys.executable, '-m', 'sv2cli', *args], cwd=ROOT, capture_output=True, timeout=60)
    (OUT / name).write_bytes(result.stdout)
    stderr = str(Path(name).with_suffix('.stderr.txt'))
    (OUT / stderr).write_bytes(result.stderr)
    commands.append({'command': ['python', '-m', 'sv2cli', *args], 'exitCode': result.returncode, 'stdout': name, 'stderr': stderr})
    return result


sources = [ROOT / 'src/sv2cli' / n for n in ['cli.py', 'score_text.py', 'loudness.py']]
before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
pitches = [60, 62, 64, 65, 67]
lyrics = ['\u4f60', '\u597d', '\u4e16', '\u754c', '+']
onsets = [0, 2, 4, 8, 12]
durations = [2, 2, 4, 4, 4]
p = apply(new_project('Hello World', 120), [{'op': 'notes.replace', 'tracks': ['#1'], 'notes': [
    {'pitch': pitch, 'lyrics': lyric, 'onset': onset * QUARTER, 'duration': duration * QUARTER}
    for pitch, lyric, onset, duration in zip(pitches, lyrics, onsets, durations)
]}], True)
p.save(OUT / 'helloworld.svp', force=True)
rate = 44100
signal = 0.75 * np.sin(2 * np.pi * 440 * np.arange(2 * rate) / rate)
pcm = np.rint(np.column_stack([signal, signal]) * 32767).astype(np.int16)
wavfile.write(OUT / 'test.wav', rate, pcm)
read_rate, data = wavfile.read(OUT / 'test.wav')
with wave.open(str(OUT / 'test.wav'), 'rb') as wav:
    wav_meta = {'sampleRate': wav.getframerate(), 'channels': wav.getnchannels(), 'frames': wav.getnframes(),
                'bitDepth': 8 * wav.getsampwidth(), 'durationSeconds': wav.getnframes() / wav.getframerate()}
fft = np.abs(np.fft.rfft(data[:, 0].astype(float)))
frequency = float(np.fft.rfftfreq(len(data), 1 / read_rate)[np.argmax(fft)])
for args, name in [(['--version'], 'version.txt'), (['doctor'], 'doctor.stdout.txt'), (['capabilities'], 'capabilities.json'),
                   (['full-score-text', '--help'], 'full-score-help.txt'), (['loudness-check', '--help'], 'loudness-help.txt'),
                   (['audio-check', '--help'], 'audio-check-help.txt')]:
    run(args, name)
requested_score = run(['inspect', 'full-score-text', 'test_verification/helloworld.svp'], 'requested-full-score.stdout.txt')
requested_loudness = run(['audio-check', 'loudness-check', 'test_verification/test.wav'], 'requested-loudness.stdout.txt')
score_run = run(['full-score-text', 'test_verification/helloworld.svp', '-o', 'test_verification/full-score-output.json', '--force'], 'full-score-stdout.json')
loudness_run = run(['loudness-check', 'test_verification/test.wav'], 'loudness-output.json')
audio_run = run(['audio-check', '--lufs', 'test_verification/test.wav'], 'audio-check-lufs-output.json')
validate_run = run(['validate', 'test_verification/helloworld.svp'], 'svp-validation.json')
score = json.loads((OUT / 'full-score-output.json').read_text(encoding='utf-8'))
loudness = json.loads(loudness_run.stdout)
audio = json.loads(audio_run.stdout)
bars = [b for t in score['tracks'] for s in t['sections'] for b in s['bars']]
notes = [n for b in bars for n in b['notes']]
intervals = [n['interval_from_prev'] for n in notes]
lufs = loudness.get('integratedLUFS')
checks = {
    'localCheckoutImported': Path(sv2cli.__file__).resolve().is_relative_to(ROOT / 'src'),
    'svpValid': validate_run.returncode == 0 and json.loads(validate_run.stdout)['valid'],
    'singleTrackFourBars': len(score['tracks']) == 1 and [b['bar'] for b in bars] == [1, 2, 3, 4],
    'tempo120AndMeter4_4': p.data['time']['tempo'] == [{'position': 0, 'bpm': 120}] and p.data['time']['meter'] == [{'index': 0, 'numerator': 4, 'denominator': 4}],
    'scoreEndsAt16QuarterBeats': max(n['onset'] + n['duration'] for n in Project.load(OUT / 'helloworld.svp').notes()) == 16 * QUARTER,
    'scoreFieldsPresent': all({'pitch', 'lyrics', 'interval_from_prev'} <= n.keys() for n in notes),
    'melodyCorrect': [n['pitch'] for n in notes] == pitches,
    'lyricsCorrect': [n['lyrics'] for n in notes] == lyrics,
    'intervalsCorrect': intervals[0] is None and [i['semitones'] for i in intervals[1:]] == [2, 2, 1, 2] and [i['name'] for i in intervals[1:]] == ['M2', 'M2', 'm2', 'M2'] and all(i['direction'] == 'up' for i in intervals[1:]),
    'wavFormatCorrect': wav_meta == {'sampleRate': 44100, 'channels': 2, 'frames': 88200, 'bitDepth': 16, 'durationSeconds': 2.0},
    'sine440HzAndIdenticalStereo': frequency == 440.0 and np.array_equal(data[:, 0], data[:, 1]),
    'supportedCommandsExitZero': all(r.returncode == 0 for r in [score_run, loudness_run, audio_run]),
    'loudnessFieldsPresent': {'integratedLUFS', 'truePeakDBFS', 'shortTermBins'} <= loudness.keys(),
    'reasonableLUFS': isinstance(lufs, (int, float)) and math.isfinite(lufs) and -4.5 <= lufs <= -1.5,
    'reasonablePeak': abs(loudness['truePeakDBFS'] - 20 * math.log10(0.75)) < 0.05,
    'shortTermBinsPresent': bool(loudness['shortTermBins']),
    'audioCheckLUFSMatches': audio.get('integratedLUFS') == lufs and audio.get('valid') is True,
    'sourceFilesUnchanged': all(hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest for path, digest in before.items()),
}
report = {
    'supportedCLIAllPassed': all(checks.values()),
    'requestedCommandSyntaxPassed': {'inspectFullScoreText': requested_score.returncode == 0, 'audioCheckLoudnessCheck': requested_loudness.returncode == 0, 'audioCheckLUFS': audio_run.returncode == 0},
    'checks': checks, 'integratedLUFS': lufs, 'truePeakDBFS': loudness['truePeakDBFS'],
    'fixture': {'wav': wav_meta, 'frequencyHz': frequency, 'peakAmplitudePerChannel': 0.75, 'quarterBeatOnsets': onsets, 'quarterBeatDurations': durations, 'lyrics': lyrics},
    'environment': {'python': sys.executable, 'packagePath': sv2cli.__file__, 'numpy': np.__version__, 'scipy': scipy.__version__, 'PYTHONPATH': os.environ['PYTHONPATH']},
    'sourceSHA256': before, 'commands': commands,
    'limitations': [
        'Ancillary doctor could not read the protected Dreamtonics app-data directory in this sandbox; its failure is saved separately.',
        'Requested nested full-score-text and loudness-check invocations fail with argparse exit 2.',
        'full-score-text writes the score to -o; stdout contains only an output/tracks receipt.',
        'Final + continues the previous syllable, preserving the four Chinese lyric characters.',
        'LUFS depends on amplitude and channel count; this fixture uses 0.75 peak per channel.',
        'For this two-second clip, shortTermBins uses a shortened window rather than a full three-second window.',
        'truePeakDBFS is the implementation linear-interpolation estimate; this does not certify BS.1770 compliance.',
        'No Synthesizer V application, plugin, or voice library was installed or loaded.'
    ]
}
save('verification-report.json', report)
print(json.dumps({k: report[k] for k in ['supportedCLIAllPassed', 'requestedCommandSyntaxPassed', 'integratedLUFS', 'truePeakDBFS', 'checks']}, indent=2))
sys.exit(0 if all(checks.values()) else 1)
