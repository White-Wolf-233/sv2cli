import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from .errors import SVError
from .io import write_json, write_new, read_json
from .project import Project
from .config import profile
from .audio import check

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
        text=log.read_text("utf8",errors="replace")[-4000:]
        raise SVError(f"Render backend exited {status}. {text}", "render_failed")

def render(source, output, profile_name="default", backend="vst3", tracks=None, stems=False, timeout=1800, warmup=15, attempts=4, tail=2, force=False, channels=2, bit_depth=16, sample_rate=44100, single_pass=False):
    original=Project.load(source)
    valid=original.validate()
    if not valid["valid"]:raise SVError(f"Project must pass validation before rendering: {valid['issues'][:4]}","invalid_project")
    output=Path(output).expanduser().resolve()
    cfg=profile(profile_name)
    if backend not in {"vst3","command"}:raise SVError("Backend must be vst3 or command")
    if backend=="vst3" and (not cfg.get("plugin") or not Path(cfg["plugin"]).exists()):
        raise SVError("VST3 instrument plugin not found. Set SV2CLI_PLUGIN or a named profile.", "plugin_missing")
    if sample_rate not in {22050,44100,48000,88200,96000}:raise SVError("Unsupported sample rate")
    if channels not in {1,2} or bit_depth not in {16,24}:raise SVError("Use 1/2 channels and PCM16/24")
    if timeout<=0 or warmup<0 or tail<0 or attempts<1:raise SVError("Invalid render limits")
    selected=original.tracks(tracks)
    if not selected:raise SVError("No tracks selected")
    tasks=[]
    if stems:
        output.mkdir(parents=True,exist_ok=True)
        for i,t in selected:
            # Numeric names are deterministic, portable and immune to slashes
            # or duplicate track names. The manifest maps them back to names.
            tasks.append(([i],output/f"{i+1:02d}.wav",t.get("name","")))
    else:tasks.append(([i for i,_ in selected],output,"MixDown"))
    manifest_path=output/"manifest.json" if stems else output.with_suffix(output.suffix+".json")
    if manifest_path.exists() and not force:raise SVError(f"Manifest exists: {manifest_path}","output_exists")
    for _,dest,_ in tasks:
        if dest.exists() and not force:raise SVError(f"Output exists: {dest}","output_exists")
        if dest.resolve()==Path(source).resolve():raise SVError("Audio output cannot replace the source project")
    job_id=uuid.uuid4().hex
    work_root=output.parent/".sv2cli-jobs"/job_id
    work_root.mkdir(parents=True,exist_ok=False)
    reports=[]
    for indices,dest,name in tasks:
        work=work_root/f"task-{len(reports)+1}";work.mkdir()
        project=original.copy()
        project.data["tracks"]=[t for i,t in project.tracks() if i in indices]
        # Single-track stems honor its gain/pan/effects, but unrelated solo flags
        # must not mute selected tracks. Explicit mute still means silence.
        if stems or tracks:
            for _,t in project.tracks():t.setdefault("mixer",{})["solo"]=False
        path=work/"project.svp";project.save(path)
        duration=project.summary()["durationSeconds"]+tail
        job={"project":str(path),"plugin":cfg.get("plugin"),"duration":duration,"work":str(work),"sampleRate":sample_rate,"channels":channels,"bitDepth":bit_depth,"warmupSeconds":warmup,"attempts":attempts,"singlePass":single_pass}
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
        write_new(dest,audio.read_bytes(),force)
        report.update(path=str(dest),trackName=name,log=str(log))
        reports.append(report)
    manifest={"jobId":job_id,"backend":backend,"source":str(Path(source).resolve()),"sourceScoreFingerprint":original.score_fingerprint(),"audio":reports,"stems":stems,"convergenceRequired":not single_pass,"warmupSeconds":warmup,"attemptLimit":attempts,"work":str(work_root),"subjectiveListeningVerified":False}
    write_json(manifest_path,manifest,force)
    return manifest
