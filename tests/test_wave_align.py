from copy import deepcopy
import numpy as np
import pytest
from sv2cli.project import new_project,QUARTER
from sv2cli.edit import apply
from sv2cli.wave_align import align,entries
from sv2cli.errors import SVError


def score():
    p=new_project('Voice',60)
    return apply(p,[{'op':'notes.replace','tracks':['#1'],'notes':[
        {'onset':QUARTER,'duration':QUARTER//2,'pitch':60,'lyrics':'la'},
        {'onset':round(2.5*QUARTER),'duration':QUARTER//2,'pitch':64,'lyrics':'ma'}]}],True)


@pytest.mark.parametrize('rate',[8000,48000])
def test_different_phrase_latencies_are_removed_without_resampling(rate):
    p=score();before=deepcopy(p.data);a=np.zeros((2,4*rate))
    for start,duration,hz in [(1.14,.5,220),(2.78,.5,330)]:
        lo=round(start*rate);n=round(duration*rate)
        a[:,lo:lo+n]=.2*np.sin(np.arange(n)*2*np.pi*hz/rate)
    result,report=align(p,a,rate,['#1'],scope='phrase')
    measured=entries(p,result,rate,['#1'])
    assert max(abs(r['delta']) for r in measured)<=.0021
    assert p.data==before and result.shape==a.shape
    assert np.max(np.abs(result))==np.max(np.abs(a))
    assert report['resampled'] is False and report['phonemeAlignmentVerified'] is False
    # Compare the actual carrier samples, not just the entry report.
    for row in report['translations']:
        dst=round(row['start']*rate);src=round((row['start']+row['advanceSeconds'])*rate)
        np.testing.assert_array_equal(result[:,dst:dst+rate//3],a[:,src:src+rate//3])


def test_sustained_audio_at_search_boundary_is_rejected():
    with pytest.raises(SVError,match='unresolved'):
        align(score(),np.ones((1,4*8000))*.1,8000,['#1'])


def test_active_leadin_cannot_be_discarded():
    rate=8000;a=np.zeros((1,rate*4));a[0,10:20]=1e-4
    for start in [1.14,2.64]:
        at=round(start*rate);a[0,at:at+rate//2]=.2
    with pytest.raises(SVError,match='leading'):
        align(score(),a,rate,['#1'])


def test_stereo_stem_remains_stereo_and_silence_is_rejected():
    with pytest.raises(SVError,match='unresolved'):
        align(score(),np.zeros((2,4*8000)),8000,['#1'])
