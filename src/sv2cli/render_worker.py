"""One native transport pass in an isolated, disposable worker."""
import json
import os
from pathlib import Path
import sys
from .errors import SVError
from .io import read_json,write_json,configure_utf8
from .project import Project


def event(kind,**fields):
    print(json.dumps({'event':kind,**fields},ensure_ascii=False),flush=True)


def run(job):
    if job.get('attempts',1)!=1:
        raise SVError('Automatic rendering retries are disabled','render_retries_disabled')
    from .native_transport import render_once
    from .render_metrics import missing_windows
    from .timing import read_pcm
    from .audio import check
    project=Project.load(job['project']);work=Path(job['work'])
    transport=render_once(job,project,event)
    target=work/'render.wav';audio,rate,_=read_pcm(target)
    expected=[];mixes={i+1:t.get('mixer',{}) for i,t in project.tracks()}
    solos={i for i,m in mixes.items() if m.get('solo')}
    for n in project.notes():
        if n['muted'] or mixes[n['track']].get('mute') or (solos and n['track'] not in solos):continue
        a=project.seconds(n['onset']);b=project.seconds(n['onset']+n['duration'])
        if b-a>.25:expected.append([a+(b-a)*.2,b-(b-a)*.2])
    missing=missing_windows(audio,rate,expected)
    coverage={'renderPasses':1,'expectedWindows':expected,'missingWindows':missing}
    write_json(work/'coverage.json',coverage)
    event('coverage',missingWindows=len(missing),expectedWindows=len(expected),missingWindowExamples=missing[:8])
    if missing:raise SVError('Single render is incomplete; inspect coverage.json. No retry or accepted output is written.','incomplete_audio')
    report=check(target,expected_seconds=job['duration'])
    if not report['valid']:raise SVError(f"Single render failed audio checks: {report['failures']}",'invalid_audio')
    report['transport']=transport;write_json(work/'result.json',report)
    event('complete',audio=str(target),renderPasses=1,automaticRetries=False)


def main():
    configure_utf8();status=0
    try:run(read_json(sys.argv[1]))
    except Exception as e:event('error',code=getattr(e,'code','render_failed'),message=str(e));status=1
    # Kill only this owned worker, including any plugin-created background threads.
    sys.stdout.flush();sys.stderr.flush();os._exit(status)


if __name__=='__main__':main()
