"""Development comparison of two retained isolated-vowel WAVs; never renders audio.

Requires NumPy and Matplotlib. Autocorrelation F0 is an acoustic proxy, with
octave/unvoiced failure modes, not a phoneme or subjective listening verdict.
"""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sv2cli.project import Project
from sv2cli.timing import read_pcm


def contour(path):
    audio,rate,_=read_pcm(path)
    # Use the channel with greatest energy; summing phase-opposed channels can cancel.
    mono=audio[int(np.argmax(np.mean(audio**2,axis=1)))];length=round(rate*.04);hop=round(rate*.002)
    window=np.hanning(length);nfft=1<<(2*length-1).bit_length();times=[];pitches=[]
    for start in range(0,len(mono)-length,hop):
        x=mono[start:start+length];rms=np.sqrt(np.mean(x*x));x=(x-np.mean(x))*window
        spectrum=np.fft.rfft(x,nfft);acf=np.fft.irfft(spectrum*np.conj(spectrum),nfft)[:length]
        low=max(2,round(rate/1000));high=min(length-2,round(rate/80))
        candidates=np.flatnonzero((acf[low:high]>acf[low-1:high-1])&(acf[low:high]>=acf[low+1:high+1]))+low
        pitch=np.nan
        if candidates.size and rms>1e-7 and acf[0]>0:
            lag=int(candidates[np.argmax(acf[candidates])]);confidence=acf[lag]/acf[0]
            if confidence>.6:
                left,center,right=acf[lag-1:lag+2];den=left-2*center+right
                refined=lag+(.5*(left-right)/den if den else 0)
                pitch=69+12*np.log2((rate/refined)/440)
        times.append((start+length/2)/rate);pitches.append(pitch)
    return np.array(times),np.array(pitches)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project');parser.add_argument('baseline');parser.add_argument('tuned');parser.add_argument('-o','--output',required=True)
    args=parser.parse_args();project=Project.load(args.project);report={'method':'40ms-Hann-autocorrelation-2ms-hop','analysisOnly':True,'subjectiveListeningVerified':False,'phonemeAlignmentVerified':False,'results':{}}
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,1,figsize=(12,6),sharex=True,sharey=True)
    for axis,(label,path) in zip(axes, [('default',args.baseline),('flat',args.tuned)]):
        times,pitches=contour(path);all_errors=[];notes=[]
        axis.plot(times,pitches,'.',markersize=1,label='estimated F0')
        for n in sorted(project.notes(),key=lambda n:n['onset']):
            a=project.seconds(n['onset']);b=project.seconds(n['onset']+n['duration']);target=n['pitch']
            ids=(times>=a+(b-a)*.25)&(times<b-(b-a)*.25)&np.isfinite(pitches)
            errors=(pitches[ids]-target)*100;all_errors.extend(errors.tolist())
            notes.append({'start':a,'end':b,'targetMidi':target,'resolvedFrames':len(errors),
                          'medianErrorCents':float(np.median(errors)) if len(errors) else None})
            axis.plot([a,b],[target,target],color='black',linewidth=.7)
            axis.axvline(a,color='grey',alpha=.3,linewidth=.5)
        errors=np.array(all_errors)
        report['results'][label]={'file':str(Path(path).resolve()),'notes':notes,
             'resolvedNotes':sum(n['resolvedFrames']>0 for n in notes),'resolvedFrames':len(errors),
             'medianAbsErrorCents':float(np.median(np.abs(errors))) if len(errors) else None,
             'framesWithin50CentsRatio':float(np.mean(np.abs(errors)<=50)) if len(errors) else None}
        axis.set_title(label);axis.set_ylabel('MIDI semitones');axis.set_ylim(58,69)
    axes[-1].set_xlabel('seconds');fig.tight_layout()
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(output.with_suffix('.png'),dpi=160)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps({k:{f:v for f,v in r.items() if f!='notes'} for k,r in report['results'].items()},indent=2))


if __name__=='__main__':main()
