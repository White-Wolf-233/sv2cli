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
    from .coverage import check as coverage_check
    from .preflight import require_monophonic
    from .timing import read_pcm
    from .audio import check
    project=Project.load(job['project']);work=Path(job['work'])
    require_monophonic(project)
    transport=render_once(job,project,event)
    target=work/'render.wav';audio,rate,_=read_pcm(target)
    coverage=coverage_check(project,audio,rate,silence_dbfs=job.get('silenceDBFS',-80),
                            max_silent_seconds=job.get('maxSilentSeconds',.5))
    coverage['renderPasses']=1
    write_json(work/'coverage.json',coverage)
    event('coverage',missingWindows=len(coverage['missingWindows']),expectedWindows=coverage['expectedNoteCount'],
          unexpectedSilence=coverage['unexpectedSilence'][:8],missingWindowExamples=coverage['missingWindows'][:8])
    if not coverage['valid']:raise SVError(f"Single render is incomplete: {len(coverage['missingWindows'])}/{coverage['expectedNoteCount']} note windows missing, {len(coverage['unexpectedSilence'])} unexpected silent spans. Inspect {work/'coverage.json'}; fix the source/plugin failure, do not retry until a lucky pass.",'incomplete_audio')
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
