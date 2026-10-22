"""Musical coordinates and measured audio timing. Energy is not phoneme truth."""
from fractions import Fraction
from pathlib import Path
import math
import wave
from .errors import SVError
from .project import QUARTER, finite, integer

def from_seconds(project, seconds):
    finite(seconds, 'seconds')
    remaining = seconds - project.data.get('time', {}).get('startTimeSeconds', 0)
    marks = project.data['time']['tempo']
    for i, mark in enumerate(marks):
        end = marks[i+1]['position'] if i+1 < len(marks) else None
        if end is None or remaining < (end-mark['position'])/QUARTER*60/mark['bpm']:
            return round(mark['position'] + remaining*mark['bpm']/60*QUARTER)
        remaining -= (end-mark['position'])/QUARTER*60/mark['bpm']

def meters(project):
    marks = project.data['time'].get('meter', [])
    if not marks or marks[0].get('index') != 0:
        raise SVError('Meter map must start at bar index 0')
    out=[]; pos=Fraction(0); last=0; num=4; den=4
    for m in marks:
        index=integer(m['index'],'bar index')
        numerator=integer(m['numerator'],'numerator')
        denominator=integer(m['denominator'],'denominator')
        if index<last or numerator<1 or denominator not in {1,2,4,8,16,32,64} or out and index==last:
            raise SVError('Invalid or unordered meter map')
        pos+=(index-last)*Fraction(num*4*QUARTER,den)
        out.append((index,pos,numerator,denominator))
        last=index;num=numerator;den=denominator
    return out

def musical(project, blick):
    marks=meters(project)
    mark=next((m for m in reversed(marks) if m[1]<=blick),marks[0])
    index,pos,num,den=mark
    beats=Fraction(blick-pos, Fraction(QUARTER*4,den))
    bars=beats//num
    beat=float(beats-bars*num+1)
    return {'bar':index+int(bars)+1,'beat':beat,'numerator':num,'denominator':den}

def position(project, value):
    if isinstance(value,(int,float)):
        return integer(value,'blick')
    if not isinstance(value,str):raise SVError('Time position must be a number or string')
    if ':' not in value:
        result=Fraction(value)
        if result.denominator!=1:raise SVError('Blick position must be an integer')
        return int(result)
    unit,text=value.split(':',1)
    if unit=='s':return from_seconds(project,float(text))
    if unit in {'q','b'}:
        result=Fraction(text)*(QUARTER if unit=='q' else 1)
        if result.denominator!=1:raise SVError('Position cannot be represented as integer blicks')
        return int(result)
    if unit=='bar':
        parts=text.split(':')
        bar=int(parts[0]);beat=Fraction(parts[1]) if len(parts)==2 else Fraction(1)
        if len(parts)>2 or bar<1:raise SVError('Use bar:N:BEAT with one-based bar and beat')
        index,pos,num,den=next(m for m in reversed(meters(project)) if m[0]<bar)
        if not 1<=beat<num+1:raise SVError(f'Beat must be in [1,{num+1}) for this bar')
        result=pos+((bar-1-index)*num+beat-1)*Fraction(QUARTER*4,den)
        if result.denominator!=1:raise SVError('Position cannot be represented as integer blicks')
        return int(result)
    raise SVError('Use b:BLICKS, q:QUARTERS, s:SECONDS or bar:N:BEAT')

def describe(project, value):
    blick=position(project,value)
    return {'blick':blick,'quarters':blick/QUARTER,'seconds':project.seconds(blick),**musical(project,blick)}

def groups(project, selectors=None):
    result=[]
    counts={}
    for _,t in project.tracks():
        for _,g in project.references(t):counts[g['uuid']]=counts.get(g['uuid'],0)+1
    for ti,t in project.tracks(selectors):
        for gi,(r,g) in enumerate(project.references(t)):
            ns=g.get('notes',[]);off=r.get('blickOffset',0)
            start=off+min((n['onset'] for n in ns),default=0)
            end=off+max((n['onset']+n['duration'] for n in ns),default=0)
            result.append({'track':ti+1,'trackName':t.get('name'),'offlineGroupIndex':gi,
                           'referenceID':r.get('uuid'),'groupID':g['uuid'],'name':g.get('name'),
                           'referenceCount':counts[g['uuid']],'notes':len(ns),'start':describe(project,start),'end':describe(project,end)})
    return result

def _numpy():
    try:import numpy as np
    except ImportError as e:raise SVError("Install audio analysis: pip install 'sv2cli[audio]'",'missing_dependency') from e
    return np

def read_pcm(path):
    np=_numpy()
    try:
        with wave.open(str(path),'rb') as f:
            rate,channels,width=f.getframerate(),f.getnchannels(),f.getsampwidth()
            raw=f.readframes(f.getnframes())
    except (wave.Error,OSError) as e:raise SVError(f'Expected integer PCM WAV: {e}','invalid_audio') from e
    if width==3:
        u=np.frombuffer(raw,np.uint8).reshape(-1,3).astype(np.int32)
        n=u[:,0]|u[:,1]<<8|u[:,2]<<16
        values=((n^0x800000)-0x800000)/8388608.
    elif width in {2,4}:values=np.frombuffer(raw,'<i2' if width==2 else '<i4').astype(np.float64)/(1<<(width*8-1))
    else:raise SVError('Timing tools support PCM16/24/32 WAV','unsupported_audio')
    return values.reshape(-1,channels).T,rate,width*8

def check(project, audio, rate, selectors, origin=0., search=.35, tolerance=.12, start=None, end=None):
    np=_numpy()
    finite(origin,'audio origin');finite(search,'search');finite(tolerance,'tolerance')
    if search<=0 or tolerance<0:raise SVError('search must be positive; tolerance nonnegative')
    range_start=position(project,start) if start is not None else None
    range_end=position(project,end) if end is not None else None
    if range_start is not None and range_end is not None and range_start>=range_end:
        raise SVError('start must be before end')
    selected=project.tracks(selectors)
    if len(selected)!=1:raise SVError('Timing analysis needs exactly one isolated stem and --track')
    ti,track=selected[0]
    if track.get('mixer',{}).get('mute'):raise SVError('Selected track is muted')
    notes=sorted((n for n in project.notes(selectors) if not n['muted']),key=lambda n:n['onset'])
    if not notes:raise SVError('Selected track has no audible notes','empty_selection')
    if not audio.size:raise SVError('Audio is empty','invalid_audio')
    hop=max(1,round(rate*.01)); energy=np.sqrt(np.mean(audio**2,axis=0))
    frames=np.array([np.sqrt(np.mean(energy[i:i+hop]**2)) for i in range(0,len(energy),hop)])
    times=np.arange(len(frames))*hop/rate
    entries=[];failures=[]
    for i,n in enumerate(notes):
        if range_start is not None and n['onset']<range_start:continue
        if range_end is not None and n['onset']>=range_end:continue
        start=project.seconds(n['onset'])-origin;end=project.seconds(n['onset']+n['duration'])-origin
        left=max(0,round((start+(end-start)*.15)*rate));right=min(audio.shape[1],round((start+(end-start)*.75)*rate))
        active=right>left and float(np.max(np.abs(audio[:,left:right])))>1e-6
        row={'uuid':n['uuid'],'referenceID':n.get('referenceID'),'lyrics':n['lyrics'],
             'expectedStartSeconds':start,'expectedEndSeconds':end,'activity':bool(active),
             'observedEntrySeconds':None,'entryDeltaSeconds':None,'observedReleaseSeconds':None,
             'status':'unresolved-legato-or-overlap'}
        if not active:failures.append({'uuid':n['uuid'],'code':'missing_activity'})
        prev_end=project.seconds(notes[i-1]['onset']+notes[i-1]['duration'])-origin if i else -math.inf
        next_start=project.seconds(notes[i+1]['onset'])-origin if i+1<len(notes) else math.inf
        if i and prev_end>start:
            row['status']='unresolved-overlap'
        elif start-prev_end>=.12:
            lo=max(0,start-search,prev_end+.04)
            hi=min(start+search,end,next_start-.02)
            ids=np.flatnonzero((times>=lo)&(times<hi))
            if len(ids):
                threshold=max(1e-5,float(np.max(frames[ids]))*.12)
                candidates=[j for j in ids if j+2<len(frames) and np.all(frames[j:j+3]>threshold)]
                if candidates:
                    j=candidates[0]
                    # Sustained energy already at the search boundary may be
                    # a previous tail, not a newly observed syllable.
                    if j>ids[0] or lo==0:
                        observed=float(times[j]);delta=observed-start
                        row.update(observedEntrySeconds=observed,entryDeltaSeconds=delta,status='energy-entry-proxy')
                        if abs(delta)>tolerance:failures.append({'uuid':n['uuid'],'code':'entry_outside_tolerance','deltaSeconds':delta})
                    else:row['status']='unresolved-active-search-boundary'
                else:row['status']='unresolved-no-sustained-entry'
        if next_start-end>=.12:
            ids=np.flatnonzero((times>=max(start,end-search))&(times<min(end+search,next_start-.04)))
            if len(ids):
                threshold=max(1e-5,float(np.max(frames[ids]))*.12)
                hits=ids[frames[ids]>threshold]
                if len(hits) and hits[-1]<ids[-1]:row['observedReleaseSeconds']=float(times[hits[-1]]+hop/rate)
        entries.append(row)
    if not entries:raise SVError('No notes in the requested timing range','empty_selection')
    measured=sum(r['observedEntrySeconds'] is not None for r in entries)
    return {'valid':not failures,'failures':failures,'track':ti+1,'audioOriginSeconds':origin,
            'notes':entries,'measuredEntries':measured,'unresolvedEntries':len(entries)-measured,
            'alignmentVerified':False,'subjectiveListeningVerified':False,
            'evidence':'Energy activity/entry/release proxies only; legato, phonemes, pitch changes and reference interpretation remain unverified.'}

def shift(project, source, output, selectors, seconds, force=False, origin=0.):
    from .pcm import encode
    from .io import write_new
    import io
    np=_numpy();finite(seconds,'shift seconds')
    if Path(source).resolve()==Path(output).resolve():raise SVError('Audio shift needs a separate output path')
    audio,rate,bits=read_pcm(source)
    if bits not in {16,24}:raise SVError('audio-shift writes PCM16/24; convert PCM32 explicitly first','unsupported_audio')
    before=check(project,audio,rate,selectors,origin)
    amount=round(seconds*rate)
    if abs(amount)>audio.shape[1]:raise SVError('Shift exceeds the audio length')
    if amount<0:
        if np.max(np.abs(audio[:,:-amount]))>1e-6:
            raise SVError('Shift would discard non-silent leading audio; render with more preroll','would_crop_audio')
        shifted=np.pad(audio[:, -amount:],((0,0),(0,-amount)))
    else:shifted=np.pad(audio,((0,0),(amount,0)))
    after=check(project,shifted,rate,selectors,origin)
    old={n['uuid']+str(n['referenceID']):n['activity'] for n in before['notes']}
    lost=[n for n in after['notes'] if old[n['uuid']+str(n['referenceID'])] and not n['activity']]
    if lost:raise SVError('Shift removes previously active note windows; no output written','timing_regression')
    buf=io.BytesIO()
    with wave.open(buf,'wb') as f:
        f.setparams((shifted.shape[0],bits//8,rate,0,'NONE','none'));f.writeframes(encode(shifted,bits))
    return {'output':write_new(output,buf.getvalue(),force),'shiftSeconds':amount/rate,
            'scoreUnchanged':True,'resampled':False,'before':before,'after':after}
