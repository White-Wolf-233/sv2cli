"""All-note activity and score-aware silence checks, independent of render attempts."""
import math
from .errors import SVError
from .project import numeric
from .preflight import audible_notes


def check(project,audio,rate,selectors=None,silence_dbfs=-80,max_silent_seconds=.5):
    import numpy as np
    numeric(silence_dbfs,'silence dBFS',-150,-20)
    numeric(max_silent_seconds,'maximum silent seconds',.02,60)
    if rate<=0 or audio.ndim!=2 or not np.isfinite(audio).all():
        raise SVError('Coverage requires finite channel-major audio and a positive sample rate','invalid_audio')
    notes=audible_notes(project,selectors)
    windows=[];missing=[];intervals=[]
    for n in notes:
        a=project.seconds(n['onset']);b=project.seconds(n['onset']+n['duration'])
        lo=a+(b-a)*.2;hi=b-(b-a)*.2
        windows.append([lo,hi]);intervals.append((a,b))
        begin=round(lo*rate);end=max(begin+1,round(hi*rate))
        if begin<0 or end>audio.shape[1] or begin>=audio.shape[1]:
            missing.append({'start':lo,'end':hi,'track':n['track'],'noteID':n['uuid'],'reason':'outside_audio'})
        elif float(np.max(np.abs(audio[:,begin:end])))<1e-6:
            missing.append({'start':lo,'end':hi,'track':n['track'],'noteID':n['uuid'],'reason':'silent_note_window'})
    # Merge score activity, never count intentional rests or the lead-in/tail.
    union=[]
    for a,b in sorted(intervals):
        if union and a<=union[-1][1]+.5/rate:union[-1][1]=max(b,union[-1][1])
        else:union.append([a,b])
    hop=max(1,round(rate*.01));threshold=10**(silence_dbfs/20);silent=[]
    for a,b in union:
        lo=max(0,round(a*rate));hi=min(audio.shape[1],round(b*rate));run=None
        for start in range(lo,hi,hop):
            end=min(start+hop,hi)
            rms=float(np.sqrt(np.mean(audio[:,start:end].astype(np.float64)**2)))
            if rms<threshold:
                if run is None:run=start
            else:
                if run is not None and (start-run)/rate>=max_silent_seconds:
                    silent.append({'start':run/rate,'end':start/rate,'duration':(start-run)/rate})
                run=None
        if run is not None and (hi-run)/rate>=max_silent_seconds:
            silent.append({'start':run/rate,'end':hi/rate,'duration':(hi-run)/rate})
    return {'valid':bool(notes) and not missing and not silent,'expectedWindows':windows,
            'expectedNoteCount':len(notes),'missingWindows':missing,'unexpectedSilence':silent,
            'silenceDBFS':silence_dbfs,'maxSilentSeconds':max_silent_seconds,
            'method':'all-note-core-activity-and-score-aware-10ms-rms',
            'individualTracksVerified':len({n['track'] for n in notes})==1,
            'allNoteOnsetsVerified':False,'phonemeAlignmentVerified':False,
            'boundary':'Activity evidence only; another voice or reverb can mask missing notes in mixed audio.'}
