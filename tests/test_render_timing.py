import json
from pathlib import Path
import wave
import numpy as np
import pytest
from sv2cli.errors import SVError
from sv2cli.project import new_project, QUARTER
from sv2cli.edit import apply
from sv2cli.pcm import encode
from sv2cli.render import render
from sv2cli.render_timing import accept
from sv2cli.wave_align import entries, write
from sv2cli.timing import read_pcm


def score():
    return apply(new_project('Voice',60),[{'op':'notes.replace','notes':[
        {'onset':QUARTER,'duration':QUARTER,'pitch':60,'lyrics':'a'},
        {'onset':3*QUARTER,'duration':QUARTER,'pitch':64,'lyrics':'a'}]}],True)


def delayed(path, seconds=.14, rate=8000, duration=5):
    a=np.zeros((2,round(duration*rate)))
    for start in (1,3):
        lo=round((start+seconds)*rate);n=round(.8*rate)
        a[:,lo:lo+n]=.1*np.sin(np.arange(n)*2*np.pi*220/rate)
    with wave.open(str(path),'wb') as w:
        w.setparams((2,3,rate,0,'NONE','none'));w.writeframes(encode(a,24))
    return a


def test_stable_delayed_audio_is_rejected_and_diagnostic_is_retained(tmp_path):
    p=score();src=tmp_path/'raw.wav';delayed(src)
    before=src.read_bytes()
    with pytest.raises(SVError) as exc:accept(p,src,tmp_path)
    assert exc.value.code=='entry_timing_mismatch'
    r=json.loads((tmp_path/'entry-timing.json').read_text())
    assert r['entriesBefore'][0]['delta']==pytest.approx(.14,abs=.003)
    assert r['firstWaveformEntryVerified'] is False and src.read_bytes()==before


def test_explicit_alignment_preserves_pcm_format_score_and_raw_source(tmp_path):
    p=score();fingerprint=p.score_fingerprint();src=tmp_path/'raw.wav'
    delayed(src);before=src.read_bytes()
    out,r=accept(p,src,tmp_path,policy='align')
    a,rate,bits=read_pcm(out)
    assert (rate,bits,a.shape)==(8000,24,(2,40000))
    assert abs(entries(p,a,rate,['#1'])[0]['delta'])<=.002
    assert r['firstWaveformEntryVerified'] and not r['allNoteOnsetsVerified']
    assert r['advanceSeconds']==pytest.approx(.14,abs=.003)
    assert p.score_fingerprint()==fingerprint and src.read_bytes()==before


def test_unresolved_or_mixed_audio_never_passes_strict_check(tmp_path):
    p=score();src=tmp_path/'raw.wav';delayed(src,seconds=.9)
    with pytest.raises(SVError) as exc:accept(p,src,tmp_path)
    assert exc.value.code=='entry_timing_unresolved'
    p=apply(p,[{'op':'track.clone','tracks':['#1']}],True)
    with pytest.raises(SVError,match='one audible stem'):accept(p,src,tmp_path,policy='align')
    _,r=accept(p,src,tmp_path,policy='report')
    assert r['status']=='unresolved' and not r['firstWaveformEntryVerified']


def test_alignment_sidecar_collision_does_not_write_audio(tmp_path):
    p=score();src=tmp_path/'raw.wav';delayed(src)
    out=tmp_path/'aligned.wav';out.with_suffix('.alignment.json').write_text('keep')
    with pytest.raises(SVError,match='exists'):write(p,src,out,['#1'])
    assert not out.exists() and out.with_suffix('.alignment.json').read_text()=='keep'


def test_first_entry_success_does_not_certify_differently_delayed_later_phrase(tmp_path):
    p=score();src=tmp_path/'raw.wav';a=delayed(src)
    # Move only the later phrase by another 80 ms.
    a[:,round(3.14*8000):]=0
    lo=round(3.22*8000);n=round(.8*8000)
    a[:,lo:lo+n]=.1*np.sin(np.arange(n)*2*np.pi*220/8000)
    with wave.open(str(src),'wb') as w:
        w.setparams((2,3,8000,0,'NONE','none'));w.writeframes(encode(a,24))
    _,r=accept(p,src,tmp_path,policy='align')
    assert r['firstWaveformEntryVerified'] and not r['allNoteOnsetsVerified']
    assert r['entriesAfter'][1]['delta']==pytest.approx(.08,abs=.003)


def test_native_acceptance_gate_runs_before_final_output_and_records_resume_policy(tmp_path,monkeypatch):
    p=score();src=tmp_path/'score.svp';p.save(src)
    plugin=tmp_path/'fake.vst3';plugin.write_bytes(b'fake')
    monkeypatch.setattr('sv2cli.render.profile',lambda name:{'plugin':str(plugin)})
    def worker(command,timeout,log):
        job=json.loads(Path(command[-1]).read_text())
        delayed(Path(job['work'])/'render.wav',rate=22050,duration=job['duration'])
    monkeypatch.setattr('sv2cli.render._worker',worker)
    target=tmp_path/'final.wav'
    with pytest.raises(SVError,match='First waveform entry'):
        render(src,target,sample_rate=22050,bit_depth=24)
    assert not target.exists()
    failed=json.loads(target.with_suffix('.wav.json').read_text())
    assert failed['status']=='failed' and failed['error']['code']=='entry_timing_mismatch'
    result=render(src,target,sample_rate=22050,bit_depth=24,force=True,entry_policy='align')
    assert result['firstWaveformEntryVerified'] and not result['allNoteOnsetsVerified']
    assert result['audio'][0]['entryTiming']['advanceSeconds']==pytest.approx(.14,abs=.003)
    resumed=render(src,target,sample_rate=22050,bit_depth=24,resume=True,entry_policy='align')
    assert resumed['audio'][0]['reused'] and resumed['firstWaveformEntryVerified']
    with pytest.raises(SVError,match='settings'):
        render(src,target,sample_rate=22050,bit_depth=24,resume=True,entry_policy='report')
