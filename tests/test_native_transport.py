import json
from pathlib import Path
import pytest
from sv2cli.errors import SVError
from sv2cli.project import QUARTER as Q
from sv2cli.native_transport import clock_maps,library_path,render_once


def test_sample_clock_maps_changing_tempo_and_meter_without_score_edits(project):
    original=project.score_fingerprint()
    project.data['time']['tempo']=[{'position':0,'bpm':120},{'position':4*Q,'bpm':60}]
    project.data['time']['meter']=[{'index':0,'numerator':4,'denominator':4},
                                  {'index':1,'numerator':3,'denominator':4},
                                  {'index':3,'numerator':6,'denominator':8}]
    before=project.score_fingerprint();tempo,meter=clock_maps(project,48000)
    assert [r['sample'] for r in tempo]==[0,96000]
    assert [(r['sample'],r['quarter']) for r in meter]==[(0,0),(96000,4),(384000,10)]
    assert project.score_fingerprint()==before and before!=original


def test_clock_accepts_off_960_grid_marks_and_rejects_ambiguous_origin(project):
    project.data['time']['tempo']=[{'position':0,'bpm':120},{'position':Q//7,'bpm':88}]
    tempo,_=clock_maps(project,44100)
    assert tempo[1]['sample']==round((Q//7)/Q*.5*44100)
    project.data['time']['startTimeSeconds']=2
    with pytest.raises(SVError) as exc:clock_maps(project,44100)
    assert exc.value.code=='unsupported_clock_origin'


def test_missing_direct_host_never_falls_back_to_drifting_host(monkeypatch):
    monkeypatch.delenv('SV2CLI_NATIVE_HOST',raising=False)
    with pytest.raises(SVError) as exc:library_path({})
    assert exc.value.code=='native_host_missing'


class Function:
    def __init__(self,fn):self.fn=fn
    def __call__(self,*args):return self.fn(*args)


@pytest.mark.parametrize('duplicate',[False,True])
def test_native_callback_protocol_requires_one_pass_and_verified_loaded_score(project,tmp_path,monkeypatch,duplicate):
    calls=[]
    def native(raw,receive):
        calls.append(1);job=json.loads(raw);work=Path(job['work'])
        (work/'native-base-state.bin').write_bytes(b'base')
        assert receive(b'{"event":"native_state_required"}')==0
        assert (work/'native-project-state.bin').read_bytes()==b'patched'
        (work/'loaded-state.bin').write_bytes(b'loaded')
        assert receive(b'{"event":"native_loaded_score_ready"}')==0
        assert receive(b'{"event":"native_single_pass","renderPasses":1}')==0
        if duplicate:
            assert receive(b'{"event":"native_single_pass","renderPasses":1}')==1
            return 1
        assert receive(b'{"event":"native_render_complete"}')==0
        return 0
    class Library:
        sv2cli_transport_abi_version=Function(lambda:1)
        sv2cli_transport_render=Function(native)
    monkeypatch.setattr('sv2cli.native_transport.ctypes.CDLL',lambda path:Library())
    monkeypatch.setattr('sv2cli.native_transport.replace_project',lambda base,data:b'patched')
    monkeypatch.setattr('sv2cli.native_transport.read_project',lambda raw:project.data)
    job={'work':str(tmp_path),'nativeHost':'mock','sampleRate':48000}
    if duplicate:
        with pytest.raises(SVError) as exc:render_once(job,project,lambda *args,**kwargs:None)
        assert exc.value.code=='render_retries_disabled'
    else:
        result=render_once(job,project,lambda *args,**kwargs:None)
        assert result['renderPasses']==1 and not result['automaticRetries']
        assert not result['audioTranslated'] and result['loadedScoreVerified']
    assert calls==[1]
