import numpy as np
import pytest

from sv2cli.config import profile
from sv2cli.edit import apply
from sv2cli.loudness import integrated_lufs, shortterm_lufs_bins, true_peak_dbfs
from sv2cli.project import QUARTER
from sv2cli.score_text import _interval


@pytest.mark.parametrize('shift', [QUARTER, -QUARTER])
def test_note_edits_keep_main_group_open_ended(project, shift):
    edited = apply(project, [{'op': 'notes.shift', 'blick': shift}], True)
    ref = edited.data['tracks'][0]['mainRef']
    assert ref['blickAbsoluteBegin'] == min(0, shift)
    assert ref['blickAbsoluteEnd'] == -1
    assert edited.validate()['valid']


def test_checkout_host_discovery_and_explicit_override(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout'
    module = checkout / 'src/sv2cli/config.py'
    module.parent.mkdir(parents=True)
    native = checkout / 'native/sv2cli_transport.dll'
    native.parent.mkdir()
    native.write_bytes(b'host')
    monkeypatch.setattr('sv2cli.config.__file__', str(module))
    monkeypatch.setattr('sv2cli.config.sys.platform', 'win32')
    monkeypatch.setattr('sv2cli.config.load_config', lambda: {'profiles': {}})
    monkeypatch.delenv('SV2CLI_NATIVE_HOST', raising=False)
    assert profile()['native_host'] == str(native)
    monkeypatch.setenv('SV2CLI_NATIVE_HOST', str(tmp_path / 'explicit.dll'))
    assert profile()['native_host'] == str(tmp_path / 'explicit.dll')


def test_true_peak_reconstructs_intersample_peak_and_final_sample():
    # Fs/4, phase pi/4 has sample peaks at 1/sqrt(2) of the sine amplitude.
    signal = 0.8 * np.sin(np.arange(4800) * np.pi / 2 + np.pi / 4)
    assert true_peak_dbfs(signal.reshape(1, -1)) > -2.1
    assert true_peak_dbfs(np.array([[0.0, 0.9]])) >= -0.92
    assert true_peak_dbfs(np.array([[0.5]])) == pytest.approx(-6.02, abs=0.01)


def test_empty_and_silent_loudness():
    empty = np.empty((1, 0))
    assert integrated_lufs(empty, 48000) is None
    assert shortterm_lufs_bins(empty, 48000) == []
    assert true_peak_dbfs(empty) is None
    assert integrated_lufs(np.zeros((2, 48000)), 48000) is None


def test_octaves_have_octave_names():
    assert _interval(0)['name'] == 'P1'
    assert _interval(12)['name'] == 'P8'
    assert _interval(-12)['direction'] == 'dn'
