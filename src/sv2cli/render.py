import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
import hashlib
from .errors import SVError
from .io import write_json, write_new, read_json
from .project import Project
from .config import profile
from .audio import check

def job_status(path):
    path=Path(path).expanduser().resolve()
    if path.is_dir():path=path/'manifest.json'
    elif path.suffix.lower()!='.json':path=path.with_suffix(path.suffix+'.json')
    manifest=read_json(path)
    if not isinstance(manifest,dict) or not isinstance(manifest.get('tasks'),list):
        raise SVError('Expected a checkpointed render manifest','invalid_manifest')
    tasks=manifest['tasks'];complete=sum(t.get('status')=='complete' for t in tasks)
    return {'jobId':manifest.get('jobId'),'status':manifest.get('status'),'completed':complete,'total':len(tasks),
            'reused':sum(bool(t.get('reused')) for t in tasks),'skipped':manifest.get('skipped',[]),
            'active':[t for t in tasks if t.get('status')=='running'],
            'failed':[t for t in tasks if t.get('status') in {'failed','cancelled'}],
            'error':manifest.get('error'),'manifest':str(path),'updatedAt':manifest.get('updatedAt'),
            'nextAction':'inspect error and resume with matching parameters' if manifest.get('status') in {'failed','cancelled'} else None}

def _checkpoint(path,manifest,force=True):
    manifest['updatedAt']=time.time()
    write_json(path,manifest,force=force)
    tasks=manifest['tasks']
    print(json.dumps({'event':'render_progress','jobId':manifest['jobId'],'status':manifest['status'],
                      'completed':sum(t.get('status')=='complete' for t in tasks),'total':len(tasks),
                      'activeTracks':[t['trackName'] for t in tasks if t.get('status')=='running'],
                      'error':manifest.get('error')},ensure_ascii=False),file=sys.stderr,flush=True)

def _worker(command, timeout, log):
    flags=subprocess.CREATE_NO_WINDOW if sys.platform=="win32" else 0
    with log.open("wb") as stream:
        process=subprocess.Popen(command,stdout=stream,stderr=subprocess.STDOUT,creationflags=flags)
        offset=0;pending=b"";start=time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic()-start>timeout:raise subprocess.TimeoutExpired(command,timeout)
                with log.open("rb") as reader:
                    reader.seek(offset);chunk=reader.read();offset+=len(chunk)
                pending+=chunk
                while b"\n" in pending:
                    line,pending=pending.split(b"\n",1)
                    try:
                        event=json.loads(line)
                        if isinstance(event,dict) and "event" in event:print(json.dumps(event,ensure_ascii=False),file=sys.stderr,flush=True)
                    except (ValueError,UnicodeError):pass
                time.sleep(.25)
            status=process.wait()
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
            raise SVError(f"Rendering stopped; worker terminated. Log: {log}", "render_timeout")
        except KeyboardInterrupt:
            process.kill();process.wait();raise
    if status:
        text=log.read_text("utf8",errors="replace")
        for line in reversed(text.splitlines()):
            try:
                value=json.loads(line)
                if isinstance(value,dict) and value.get('event')=='error':
                    raise SVError(f"{value.get('message','Render failed')}; worker log: {log}",value.get('code','render_failed'))
            except (ValueError,UnicodeError):pass
        raise SVError(f"Render backend exited {status}. {text[-4000:]}", "render_failed")

def render(source, output, profile_name="default", backend="vst3", tracks=None, stems=False, timeout=1800, warmup=15, attempts=1, tail=2, force=False, channels=2, bit_depth=16, sample_rate=44100, single_pass=False, resume=False, entry_policy=None, entry_tolerance=.03,entry_landmark='broadband',target_peak=None,silence_dbfs=-80,max_silent_seconds=.5):
    original=Project.load(source)
    valid=original.validate()
    if not valid["valid"]:raise SVError(f"Project must pass validation before rendering: {valid['issues'][:4]}","invalid_project")
    output=Path(output).expanduser().resolve()
    cfg=profile(profile_name)
    if backend not in {"vst3","command"}:raise SVError("Backend must be vst3 or command")
    from .project import finite,numeric
    entry_policy=entry_policy or 'report'
    finite(entry_tolerance,'entry tolerance')
    for value,label in [(timeout,'timeout'),(warmup,'warmup'),(tail,'tail')]:finite(value,label)
    numeric(silence_dbfs,'silence dBFS',-150,-20);numeric(max_silent_seconds,'maximum silent seconds',.02,60)
    if target_peak is not None:numeric(target_peak,'target peak dBFS',-60,-.1)
    if entry_policy not in {'check','align','report'} or entry_tolerance<.002:
        raise SVError('Use check/align/report and an entry tolerance of at least 2 ms')
    if entry_landmark not in {'broadband','voiced'}:raise SVError('Entry landmark must be broadband or voiced')
    if backend=="vst3" and (not cfg.get("plugin") or not Path(cfg["plugin"]).exists()):
        raise SVError("VST3 instrument plugin not found. Set SV2CLI_PLUGIN or a named profile.", "plugin_missing")
    if sample_rate not in {22050,44100,48000,88200,96000}:raise SVError("Unsupported sample rate")
    if channels not in {1,2} or bit_depth not in {16,24}:raise SVError("Use 1/2 channels and PCM16/24")
    if timeout<=0 or warmup<0 or tail<0 or attempts<1:raise SVError("Invalid render limits")
    if attempts!=1:raise SVError('Automatic render retries are disabled. Use one pass; inspect failures rather than selecting a lucky render.','render_retries_disabled')
    native_host=None
    if backend=='vst3':
        from .native_transport import library_path
        native_host=library_path(cfg)
    selected=original.tracks(tracks)
    if not selected:raise SVError("No tracks selected")
    if resume and force:raise SVError('Use --resume or --force, not both')
    tasks=[]
    skipped=[]
    if stems:
        output.mkdir(parents=True,exist_ok=True)
        for i,t in selected:
            reason='muted' if t.get('mixer',{}).get('mute') else 'render_disabled' if not t.get('renderEnabled',True) else 'empty' if not any(not n['muted'] for n in original.notes([f'#{i+1}'])) else None
            if reason:
                skipped.append({'track':i+1,'name':t.get('name',''),'reason':reason})
                continue
            # Numeric names are deterministic, portable and immune to slashes
            # or duplicate track names. The manifest maps them back to names.
            tasks.append(([i],output/f"{i+1:02d}.wav",t.get("name","")))
    else:tasks.append(([i for i,_ in selected],output,"MixDown"))
    manifest_path=output/"manifest.json" if stems else output.with_suffix(output.suffix+".json")
    if manifest_path.resolve()==Path(source).resolve():raise SVError('Manifest cannot replace the source project')
    if not tasks:raise SVError('No audible tracks to render; empty/muted/disabled stems were skipped','empty_selection')
    plugin_identity=None
    if cfg.get('plugin') and Path(cfg['plugin']).exists():
        stat=Path(cfg['plugin']).stat()
        plugin_identity={'size':stat.st_size,'modifiedNs':stat.st_mtime_ns}
    from . import __version__
    request={'acceptanceRevision':'all-note-rms-v1','version':__version__,'project':original.data,'config':cfg,'pluginIdentity':plugin_identity,
             'backend':backend,'tracks':[i for i,_ in selected],'stems':stems,
             'sampleRate':sample_rate,'channels':channels,'bitDepth':bit_depth,
             'tail':tail,'warmup':warmup,'attempts':attempts,'singlePass':single_pass,
             'entryPolicy':entry_policy,'entryTolerance':entry_tolerance,'entryLandmark':entry_landmark,
             'targetPeakDBFS':target_peak,'silenceDBFS':silence_dbfs,'maxSilentSeconds':max_silent_seconds,
             'nativeHostSHA256':hashlib.sha256(Path(native_host).read_bytes()).hexdigest() if native_host else None}
    request_key=hashlib.sha256(json.dumps(request,sort_keys=True,allow_nan=False).encode()).hexdigest()
    prior=read_json(manifest_path) if resume and manifest_path.exists() else None
    if resume and (prior is None or prior.get('requestFingerprint')!=request_key):
        raise SVError('No matching checkpoint: source/settings/backend changed, or manifest is missing. Use a new output or --force.','resume_mismatch')
    if manifest_path.exists() and not (force or resume):raise SVError(f"Manifest exists: {manifest_path}","output_exists")
    for _,dest,_ in tasks:
        if dest.exists() and not (force or resume):raise SVError(f"Output exists: {dest}","output_exists")
        if dest.resolve()==Path(source).resolve():raise SVError("Audio output cannot replace the source project")
    job_id=uuid.uuid4().hex
    work_root=output.parent/".sv2cli-jobs"/job_id
    work_root.mkdir(parents=True,exist_ok=False)
    reports=[]
    prior_audio=(prior.get('checkpointAudio') or prior.get('audio',[])) if prior else []
    manifest={"jobId":job_id,"backend":backend,"source":str(Path(source).resolve()),"sourceScoreFingerprint":original.score_fingerprint(),
              'requestFingerprint':request_key,'status':'running','audio':reports,'checkpointAudio':list(prior_audio),'tasks':[], 'skipped':skipped,
              'stems':stems,'loadedScoreVerified':False,'expectedActivityChecked':False,
              'convergenceRequired':False,'renderPassesPerTask':1,'warmupSeconds':warmup,'attemptLimit':1,
              'work':str(work_root),'subjectiveListeningVerified':False}
    manifest.update(entryPolicy=entry_policy,entryToleranceSeconds=entry_tolerance,
                    firstWaveformEntryVerified=False,allNoteOnsetsVerified=False,
                    transport='direct-vst3-sample-clock' if backend=='vst3' else 'command',automaticRetries=False,
                    nativeHostSHA256=request['nativeHostSHA256'])
    manifest['entryLandmark']=entry_landmark
    manifest.update(targetPeakDBFS=target_peak,silenceDBFS=silence_dbfs,maxSilentSeconds=max_silent_seconds)
    for indices,dest,name in tasks:manifest['tasks'].append({'tracks':[i+1 for i in indices],'path':str(dest),'trackName':name,'status':'pending'})
    _checkpoint(manifest_path,manifest,force=force or resume)
    def digest(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
        return h.hexdigest()
    try:
        return _tasks(original,source,tasks,manifest,manifest_path,prior,reports,work_root,cfg,backend,
                      timeout,warmup,attempts,tail,force,channels,bit_depth,sample_rate,single_pass,tracks,stems,digest,entry_policy,entry_tolerance,native_host,entry_landmark)
    except (Exception,KeyboardInterrupt) as error:
        manifest['status']='cancelled' if isinstance(error,KeyboardInterrupt) else 'failed'
        for task in manifest['tasks']:
            if task['status']=='running':task['status']=manifest['status']
        manifest['error']={'code':getattr(error,'code','render_failed'),'message':str(error)}
        _checkpoint(manifest_path,manifest)
        raise

def _tasks(original,source,tasks,manifest,manifest_path,prior,reports,work_root,cfg,backend,
           timeout,warmup,attempts,tail,force,channels,bit_depth,sample_rate,single_pass,tracks,stems,digest,entry_policy,entry_tolerance,native_host,entry_landmark):
    for indices,dest,name in tasks:
        task=manifest['tasks'][len(reports)]
        old=next((r for r in (prior.get('checkpointAudio') or prior.get('audio',[])) if r.get('path')==str(dest)),None) if prior else None
        if old and dest.exists() and old.get('sha256')==digest(dest):
            report=check(dest,expected_seconds=old['durationSeconds'])
            if report['valid'] and (report['sampleRate'],report['channels'],report['bitDepth'])==(sample_rate,channels,bit_depth):
                reports.append({**old,'reused':True});task['status']='complete';task['reused']=True
                _checkpoint(manifest_path,manifest)
                continue
        # Never clobber an unrelated or externally modified file on resume.
        if dest.exists() and not force:
            raise SVError(f'Existing output cannot be verified for resume: {dest}. Use --force or move it aside.','resume_output_conflict')
        task['status']='running'
        _checkpoint(manifest_path,manifest)
        work=work_root/f"task-{len(reports)+1}";work.mkdir()
        project=original.copy()
        project.data["tracks"]=[t for i,t in project.tracks() if i in indices]
        if backend == 'vst3':
            for _, track in project.tracks():
                ref = track.get('mainRef')
                if ref is not None:
                    notes = track.get('mainGroup', {}).get('notes', [])
                    begin = ref.get('blickOffset', 0) + min((n['onset'] for n in notes), default=0)
                    ref.update(blickAbsoluteBegin=min(0, begin), blickAbsoluteEnd=-1)
        # A stem needs only the selected tracks' library references. Loading
        # orphaned groups keeps unrelated native synthesis/cache state alive.
        # The user's source library remains untouched.
        referenced={ref.get("groupID") for _,t in project.tracks() for ref in t.get("groups",[])}
        referenced.update(t.get("mainRef",{}).get("groupID") for _,t in project.tracks())
        project.data["library"]=[g for g in project.data.get("library",[]) if g.get("uuid") in referenced]
        # Single-track stems honor its gain/pan/effects, but unrelated solo flags
        # must not mute selected tracks. Explicit mute still means silence.
        if stems or tracks:
            for _,t in project.tracks():t.setdefault("mixer",{})["solo"]=False
        from .preflight import require_monophonic
        preflight=require_monophonic(project)
        write_json(work/'preflight.json',preflight)
        for _,t in project.tracks():
            if not t.get("renderEnabled",True):t.setdefault("mixer",{}).update(mute=True,solo=False)
        path=work/"project.svp";project.save(path)
        duration=original.summary()["durationSeconds"]+tail
        job={"project":str(path),"plugin":cfg.get("plugin"),"duration":duration,"work":str(work),"sampleRate":sample_rate,"channels":channels,"bitDepth":bit_depth,"warmupSeconds":warmup,"attempts":attempts,"singlePass":single_pass}
        if native_host:job['nativeHost']=native_host
        job.update(silenceDBFS=manifest['silenceDBFS'],maxSilentSeconds=manifest['maxSilentSeconds'])
        job_path=work/"job.json";write_json(job_path,job)
        log=work/"worker.log"
        if backend=="vst3":
            command=[sys.executable,"-m","sv2cli.render_worker",str(job_path)]
        else:
            template=cfg.get("render_command")
            if not isinstance(template,list) or not template or not all(isinstance(a,str) for a in template):
                raise SVError("Command backend needs profile.render_command as an argv array", "backend_unconfigured")
            mapping={"project":str(path),"output":str(work/"render.wav"),"job":str(job_path),"duration":str(duration)}
            try:command=[a.format_map(mapping) for a in template]
            except KeyError as e:raise SVError(f"Unknown command placeholder: {e}") from e
        _worker(command,timeout,log)
        audio=work/"render.wav"
        report=check(audio,expected_seconds=duration)
        if not report["valid"]:raise SVError(f"Render failed audio checks: {report['failures']}; log: {log}","invalid_audio")
        if (report["sampleRate"],report["channels"],report["bitDepth"])!=(sample_rate,channels,bit_depth):
            raise SVError(f"Backend output format does not match the requested {sample_rate} Hz / {channels} channel(s) / PCM{bit_depth}; log: {log}","format_mismatch")
        # Readiness/coverage and a plugin-reported zero latency do not establish
        # waveform timing. Check the actual PCM before accepting the output.
        # Report-only command backends retain dependency-free operation.
        timing={'policy':entry_policy,'status':'unchecked','firstWaveformEntryVerified':False}
        native_result=read_json(work/'result.json').get('transport') if backend=='vst3' and (work/'result.json').exists() else None
        if backend=='vst3' or entry_policy!='report':
            from .render_timing import accept
            audio,timing=accept(project,audio,work,entry_policy,entry_tolerance,entry_landmark)
            report=check(audio,expected_seconds=duration)
            if not report['valid']:raise SVError('Aligned output failed audio validation','invalid_audio')
        normalization=None
        if manifest['targetPeakDBFS'] is not None:
            from .normalize import write as normalize
            normalized=work/'normalized.wav'
            normalization=normalize(audio,normalized,manifest['targetPeakDBFS'])
            audio=normalized;report=check(audio,expected_seconds=duration)
            if not report['valid']:raise SVError('Normalized output failed validation','invalid_audio')
        write_new(dest,audio.read_bytes(),force)
        report.update(path=str(dest),trackName=name,log=str(log),sha256=digest(dest),reused=False,entryTiming=timing,nativeTransport=native_result,normalization=normalization,preflight=preflight)
        reports.append(report)
        manifest['checkpointAudio']=[r for r in manifest['checkpointAudio'] if r.get('path')!=str(dest)]+[report]
        task['status']='complete'
        _checkpoint(manifest_path,manifest)
    manifest.update(status='complete',loadedScoreVerified=backend=='vst3',expectedActivityChecked=backend=='vst3')
    manifest['firstWaveformEntryVerified']=all(r.get('entryTiming',{}).get('firstWaveformEntryVerified',False) for r in reports)
    _checkpoint(manifest_path,manifest)
    return manifest
