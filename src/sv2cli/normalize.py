"""Explicit sample-peak gain only: no timing shift, limiting or resampling."""
import math
import wave
from pathlib import Path
from .errors import SVError
from .project import numeric
from .timing import read_pcm
from .pcm import encode
from .io import write_new


def write(source,output,target_dbfs=-1,force=False):
    import io
    import numpy as np
    numeric(target_dbfs,'target peak dBFS',-60,-.1)
    if Path(source).resolve()==Path(output).resolve():raise SVError('Normalization requires a new output path','source_protected')
    audio,rate,bits=read_pcm(source)
    if bits not in {16,24}:raise SVError('Normalization supports PCM16/24; convert other formats explicitly first','unsupported_audio')
    if not np.isfinite(audio).all():raise SVError('Cannot normalize nonfinite audio','invalid_audio')
    peak=float(np.max(np.abs(audio))) if audio.size else 0
    if peak<1e-12:raise SVError('Cannot normalize silent audio','silent_audio')
    target=10**(target_dbfs/20);gain=target/peak
    memory=io.BytesIO()
    with wave.open(memory,'wb') as f:
        f.setparams((audio.shape[0],bits//8,rate,0,'NONE','none'));f.writeframes(encode(audio*gain,bits))
    result=write_new(output,memory.getvalue(),force)
    return {'output':result,'targetPeakDBFS':target_dbfs,'inputPeakDBFS':20*math.log10(peak),
            'gainDB':20*math.log10(gain),'gainLinear':gain,'frames':audio.shape[1],
            'sampleRate':rate,'bitDepth':bits,'channels':audio.shape[0],
            'audioTranslated':False,'resampled':False,'method':'sample-peak-gain',
            'truePeakVerified':False,'loudnessNormalized':False}
