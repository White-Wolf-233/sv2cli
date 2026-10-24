"""Measured phrase entry alignment for a dry, isolated vocal stem.

Only PCM samples move. No score, tempo, pitch or sample rate is changed.
Entry landmarks are waveform energy, not phoneme or F0 ground truth.
"""
from pathlib import Path
import io, math, wave
from .errors import SVError
from .timing import _numpy, read_pcm
from .project import finite


def phrases(project, selectors, gap=.35, origin=0.):
    tracks=project.tracks(selectors)
    if len(tracks)!=1:raise SVError('wave-align needs one isolated stem and exactly one --track')
    if tracks[0][1].get('mixer',{}).get('mute'):raise SVError('Selected track is muted')
    notes=sorted((n for n in project.notes(selectors) if not n['muted']),key=lambda n:n['onset'])
    if not notes:raise SVError('Selected track has no audible notes','empty_selection')
    result=[]
    for n in notes:
        a=project.seconds(n['onset'])-origin;b=project.seconds(n['onset']+n['duration'])-origin
        if not result or a-result[-1]['end']>=gap:
            result.append({'start':a,'end':b,'firstEnd':b,'firstID':n['uuid'],'lyrics':n['lyrics'],'notes':[n]})
        else:
            result[-1]['end']=max(result[-1]['end'],b);result[-1]['notes'].append(n)
    return result


def rms_envelope(audio,rate):
    np=_numpy();hop=max(1,round(rate*.002));n=audio.shape[1]
    mono=np.mean(audio*audio,axis=0)
    padded=np.pad(mono,(0,(-n)%hop))
    energy=np.sqrt(padded.reshape(-1,hop).mean(axis=1))
    return np.arange(len(energy))*hop/rate,energy,hop


def entry_envelope(audio,rate,landmark):
    if landmark=='broadband':return rms_envelope(audio,rate)
    if landmark!='voiced':raise SVError('Entry landmark must be broadband or voiced')
    # Explicit low-band voicing proxy, not a phoneme classifier. A centered
    # 20-ms window avoids a causal filter delay; 2-ms hops match the RMS report.
    # Process bounded batches and retain stereo power (no phase-cancelling sum).
    np=_numpy();hop=max(1,round(rate*.002));width=max(16,round(rate*.020))
    count=(audio.shape[1]+hop-1)//hop;window=np.hanning(width)
    bands=(np.fft.rfftfreq(width,1/rate)>=80)&(np.fft.rfftfreq(width,1/rate)<=1600)
    padded=np.pad(audio,((0,0),(width//2,width)))
    result=np.empty(count)
    for first in range(0,count,512):
        size=min(512,count-first);begin=first*hop;end=begin+(size-1)*hop+width
        frames=np.lib.stride_tricks.sliding_window_view(padded[:,begin:end],width,axis=1)[:,::hop,:]
        spectrum=np.fft.rfft(frames*window,axis=-1)
        power=(np.abs(spectrum[...,bands])**2).sum(axis=-1)*2/(width*np.sum(window**2))
        result[first:first+size]=np.sqrt(power.mean(axis=0))
    return np.arange(count)*hop/rate,result,hop


def entries(project,audio,rate,selectors,gap=.35,search=.7,threshold=.12,origin=0.,landmark='broadband'):
    np=_numpy()
    finite(rate,'sample rate')
    if rate<=0 or int(rate)!=rate:raise SVError('Sample rate must be a positive integer')
    for x,label in [(gap,'phrase gap'),(search,'search'),(threshold,'threshold'),(origin,'origin')]:finite(x,label)
    if gap<=0 or search<=0 or not 0<threshold<1:raise SVError('Invalid waveform entry limits')
    if audio.ndim!=2 or audio.shape[0] not in {1,2} or not audio.size or not np.isfinite(audio).all():raise SVError('Invalid or empty mono/stereo PCM samples')
    groups=phrases(project,selectors,gap,origin);times,energy,hop=entry_envelope(audio,rate,landmark)
    result=[]
    for i,g in enumerate(groups):
        prior=groups[i-1]['end'] if i else -math.inf
        # Never hunt into the preceding phrase's written sustain.
        lo=max(0,g['start']-search,prior+.04)
        hi=min(g['start']+search,max(g['firstEnd']+.15,g['start']+.4),g['end'])
        ids=np.flatnonzero((times>=lo)&(times<hi))
        row={k:v for k,v in g.items() if k!='notes'};row.update(observed=None,delta=None,landmark=landmark)
        if len(ids):
            peak=float(energy[ids].max());level=max(1e-6,peak*threshold)
            hits=[k for k in ids if k+2<len(energy) and np.all(energy[k:k+3]>level)]
            if hits and (hits[0]>ids[0] or lo==0):
                row.update(observed=float(times[hits[0]]),delta=float(times[hits[0]]-g['start']),threshold=level)
        result.append(row)
    return result


def align(project,audio,rate,selectors,gap=.35,search=.7,threshold=.12,origin=0.,tolerance=.008,scope='track',landmark='broadband'):
    np=_numpy();finite(tolerance,'tolerance')
    if tolerance<.002:raise SVError('Tolerance must be at least the 2ms waveform envelope resolution')
    if scope not in {'track','phrase'}:raise SVError('Scope must be track or phrase')
    all_entries=entries(project,audio,rate,selectors,gap,search,threshold,origin,landmark)
    before=all_entries[:1] if scope=='track' else all_entries
    if any(r['observed'] is None for r in before):
        raise SVError('An entry is unresolved or already active at the search boundary; inspect waveforms before alignment','unresolved_entry')
    groups=phrases(project,selectors,gap,origin)
    if scope=='track':groups=[{**groups[0],'end':groups[-1]['end']}]
    offsets=[round(r['delta']*rate) for r in before]
    times,energy,hop=rms_envelope(audio,rate)
    boundaries=[0]
    for i in range(1,len(groups)):
        lo=round((groups[i-1]['end']+.03)*rate);hi=round((groups[i]['start']-.03)*rate)
        candidates=np.arange(max(0,lo),min(audio.shape[1],hi),hop,dtype=int)
        if not len(candidates):raise SVError('No safe rest boundary between phrases','unsafe_boundary')
        # Both translations must meet in silence, rather than cutting a tail.
        left=np.clip((candidates+offsets[i-1])//hop,0,len(energy)-1)
        right=np.clip((candidates+offsets[i])//hop,0,len(energy)-1)
        cost=np.maximum(energy[left],energy[right])
        k=int(np.argmin(cost));boundary=int(candidates[k])
        local=max(before[i-1]['threshold'],before[i]['threshold'])
        if cost[k]>max(1e-5,local*.2):
            raise SVError('Phrase offsets would splice active audio; use a larger region or explicit reviewed anchors','unsafe_boundary')
        # Different translations skip or duplicate the source interval between
        # the cuts. Quiet endpoints alone cannot establish that interval is safe.
        cut_a,cut_b=sorted((boundary+offsets[i-1],boundary+offsets[i]))
        if np.max(np.abs(audio[:,max(0,cut_a):min(audio.shape[1],cut_b)]),initial=0)>1e-6:
            raise SVError('Phrase translations would skip or duplicate active audio','unsafe_boundary')
        boundaries.append(boundary)
    boundaries.append(audio.shape[1]);out=np.zeros_like(audio)
    moved=[]
    for i,(a,b) in enumerate(zip(boundaries,boundaries[1:])):
        offset=offsets[i];src_a=a+offset;src_b=b+offset
        cut_lo=max(0,-src_a);cut_hi=max(0,src_b-audio.shape[1])
        if cut_lo and np.max(np.abs(audio[:,:max(0,src_a+cut_lo)]),initial=0)>1e-6:
            raise SVError('Alignment would crop active leading audio','would_crop_audio')
        if src_a>0 and i==0 and np.max(np.abs(audio[:,:src_a]),initial=0)>1e-6:
            raise SVError('Alignment would crop active leading audio','would_crop_audio')
        if i==len(groups)-1 and src_b<audio.shape[1] and np.max(np.abs(audio[:,max(0,src_b):]),initial=0)>1e-6:
            raise SVError('Alignment would crop active trailing audio','would_crop_audio')
        target_a=a+cut_lo;target_b=b-cut_hi
        if target_b>target_a:out[:,target_a:target_b]=audio[:,src_a+cut_lo:src_b-cut_hi]
        moved.append({'firstID':before[i]['firstID'],'start':before[i]['start'],'end':before[i]['end'],'advanceSeconds':offset/rate,'sourceObservedEntry':before[i]['observed'],'boundarySamples':[a,b]})
    all_after=entries(project,out,rate,selectors,gap,search,threshold,origin,landmark)
    after=all_after[:1] if scope=='track' else all_after
    for r in after:
        if r['observed'] is None or abs(r['delta'])>tolerance:
            raise SVError('Waveform entry did not converge to the written anchor','alignment_failed')
    # Every previously active note interior must remain active.
    for n in project.notes(selectors):
        a=project.seconds(n['onset'])-origin;b=project.seconds(n['onset']+n['duration'])-origin
        lo=max(0,round((a+(b-a)*.2)*rate));hi=min(audio.shape[1],round((a+(b-a)*.8)*rate))
        if hi>lo and np.max(np.abs(audio[:,lo:hi]))>1e-6 and np.max(np.abs(out[:,lo:hi]))<=1e-6:
            raise SVError('Alignment emptied a previously active note','timing_regression')
    report={'method':scope+'-waveform-entry-translation','landmark':landmark,'scope':scope,'before':before,'after':after,'allObservedEntriesBefore':all_entries,'allObservedEntriesAfter':all_after,'translations':moved,'sampleRate':rate,'frames':audio.shape[1],'maximumEntryErrorSeconds':max(abs(r['delta']) for r in after),'scoreUnchanged':True,'resampled':False,'pitchShifted':False,'waveformEntriesWithinTolerance':True,'allNoteOnsetsVerified':False,'phonemeAlignmentVerified':False,'subjectiveListeningVerified':False}
    return out,report


def write(project,source,output,selectors,force=False,**kwargs):
    from .pcm import encode
    from .io import write_new,write_json
    output=Path(output);sidecar=output.with_suffix('.alignment.json')
    if Path(source).resolve() in {output.resolve(),sidecar.resolve()}:raise SVError('Use a separate aligned output and report')
    if output.resolve()==sidecar.resolve():raise SVError('Audio and alignment report must have separate paths')
    for target in (output,sidecar):
        if target.exists() and not force:raise SVError(f'Output exists: {target}','output_exists')
    audio,rate,bits=read_pcm(source)
    if bits not in {16,24}:raise SVError('wave-align writes PCM16/24','unsupported_audio')
    aligned,report=align(project,audio,rate,selectors,**kwargs)
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:
        w.setparams((aligned.shape[0],bits//8,rate,0,'NONE','none'));w.writeframes(encode(aligned,bits))
    write_new(output,buf.getvalue(),force)
    report.update(source=str(source),output=str(output),scoreFingerprint=project.score_fingerprint())
    write_json(sidecar,report,force=force)
    return report
