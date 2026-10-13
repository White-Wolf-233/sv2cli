import pytest
np=pytest.importorskip("numpy")
from sv2cli.render_metrics import envelope,convergence,missing_windows
from sv2cli.pcm import encode

def test_phase_randomness_is_not_synthesis_progress():
    t=np.arange(8000)/8000
    a=np.array([np.sin(t*2*np.pi*200)])
    b=np.array([np.sin(t*2*np.pi*200+1.5)])
    assert convergence(envelope(a,8000),envelope(b,8000))<1e-10

def test_missing_tail_note_detected():
    a=np.ones((2,8000));a[:,4000:]=0
    assert missing_windows(a,8000,[[.1,.4],[.6,.9]])==[[.6,.9]]

def test_partial_render_changes_envelope():
    a=np.ones((2,8000));b=a.copy();b[:,4000:]=0
    assert convergence(envelope(a,8000),envelope(b,8000))>.005

@pytest.mark.parametrize("bits",[16,24])
def test_pcm_interleaving_and_signed_samples_from_noncontiguous_array(bits):
    audio=np.array([[0,-1,.5],[.25,-.5,1]],dtype=np.float32)
    b=encode(audio,bits);width=bits//8
    values=[int.from_bytes(b[i:i+width],"little",signed=True) for i in range(0,len(b),width)]
    scale=1<<(bits-1)
    assert values==[0,scale//4,-scale,-scale//2,scale//2,scale-1]
