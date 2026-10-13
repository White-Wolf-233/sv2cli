"""Native plugins live in a disposable worker, never the CLI process."""
import json
import os
from pathlib import Path
import sys
import time
import wave
from .errors import SVError
from .io import read_json, write_json,configure_utf8
from .project import Project, QUARTER
from .plugin_state import replace_project,read_project

def event(kind, **fields):
    print(json.dumps({"event":kind,**fields},ensure_ascii=False),flush=True)

def run(job):
    try:
        import dawdreamer as daw
        import numpy as np
    except ImportError as e:
        raise SVError("Install rendering dependencies: pip install 'sv2cli[render]'", "missing_dependency") from e
    project=Project.load(job["project"])
    from .event_loop import EventLoop
    from .render_metrics import envelope,convergence,missing_windows
    loop=EventLoop()
    plugin_path=job["plugin"]
    sample_rate=job.get("sampleRate",44100)
    duration=job["duration"]
    work=Path(job["work"])
    event("loading_plugin",path=plugin_path)
    engine=daw.RenderEngine(sample_rate,job.get("bufferSize",512))
    plugin=engine.make_plugin_processor("sv2cli",plugin_path)
    state_path=work/"state.bin"
    plugin.save_state(str(state_path))
    state=replace_project(state_path.read_bytes(),project.data)
    state_path.write_bytes(state)
    plugin.load_state(str(state_path))
    event("project_loaded",notes=len(project.notes()))
    marks=project.data["time"]["tempo"]
    if len(marks)==1:
        engine.set_bpm(float(marks[0]["bpm"]))
    else:
        # Hosts may override project tempo. Supply the same tempo map, at a
        # 1/960-quarter grid. Fail if a mark cannot be represented exactly.
        ppqn=960
        end=project.summary()["endBlick"]
        bpm=np.full(max(1,round(end/QUARTER*ppqn)+ppqn*16),marks[0]["bpm"],dtype=np.float32)
        for m in marks:
            tick=m["position"]*ppqn/QUARTER
            if abs(tick-round(tick))>1e-6:
                raise SVError("Tempo mark is off the host's 1/960-quarter grid", "unsupported_tempo_grid")
            bpm[round(tick):]=m["bpm"]
        engine.set_bpm(bpm,ppqn)
    engine.load_graph([(plugin,[])])
    warmup=job.get("warmupSeconds",15)
    event("warming_up",seconds=warmup)
    # Short waits are reported; the parent remains responsive and can cancel.
    deadline=time.monotonic()+warmup
    while time.monotonic()<deadline:
        loop.wait(min(1,max(0,deadline-time.monotonic())))
    plugin.save_state(str(work/"loaded-state.bin"))
    loaded=Project(read_project((work/"loaded-state.bin").read_bytes()))
    if loaded.score_fingerprint()!=project.score_fingerprint():
        raise SVError("Plugin did not load the requested score; output is rejected", "project_load_mismatch")
    event("loaded_score_verified",notes=len(loaded.notes()))
    expected=[]
    track_mix={i+1:t.get("mixer",{}) for i,t in project.tracks()}
    solos={i for i,m in track_mix.items() if m.get("solo")}
    for n in project.notes():
        m=track_mix[n["track"]]
        if n["muted"] or m.get("mute") or solos and n["track"] not in solos:continue
        a=project.seconds(n["onset"]);b=project.seconds(n["onset"]+n["duration"])
        if b-a>.25:expected.append([a+(b-a)*.2,b-(b-a)*.2])
    best=None;last=None;stable=0
    attempts=job.get("attempts",4)
    for attempt in range(attempts):
        event("rendering",attempt=attempt+1,duration=duration)
        loop.run_background(lambda:engine.render(duration))
        audio=engine.get_audio()
        if audio.ndim!=2 or audio.shape[0]<1 or not np.isfinite(audio).all():
            raise SVError("Plugin returned invalid audio", "invalid_audio")
        # The SV2 instrument exposes a 32-channel output: master stereo first,
        # followed by track buses. Render the master, never average all buses.
        audio=audio[:2]
        peak=float(np.max(np.abs(audio))) if audio.size else 0
        rms=float(np.sqrt(np.mean(audio**2))) if audio.size else 0
        event("render_pass",attempt=attempt+1,peak=peak,rms=rms)
        missing=missing_windows(audio,sample_rate,expected)
        event("coverage",missingWindows=len(missing),expectedWindows=len(expected))
        current=envelope(audio,sample_rate)
        if peak>job.get("minPeak",1e-6) and not missing:
            best=audio.copy()
            # Async synthesis can produce an incomplete first pass. Require two
            # sufficiently similar non-silent passes unless explicitly disabled.
            relative=convergence(last,current)
            if relative is not None:
                stable=stable+1 if relative<.005 else 0
                event("convergence",energyEnvelopeError=relative,stablePasses=stable)
            last=current
            if stable>=1 or job.get("singlePass",False):break
        if attempt+1<attempts:loop.wait(job.get("retryDelay",5))
    if best is None:
        raise SVError("Plugin produced silence. Check voice activation and plugin compatibility; no successful output is written.", "silent_audio")
    if stable<1 and not job.get("singlePass",False):
        if best is not None:np.save(work/"failed-audio.npy",best)
        raise SVError("Audio did not stabilize before the attempt limit. Increase --attempts/--warmup; no successful output is written.", "render_not_ready")
    channels=job.get("channels",2)
    if channels==1:best=np.mean(best,axis=0,keepdims=True)
    elif best.shape[0]==1:best=np.repeat(best,2,axis=0)
    peak=float(np.max(np.abs(best)))
    if peak>=1 and not job.get("allowClipping",False):
        raise SVError(f"Mix peaks at {peak:.3f}; reduce track gains before rendering", "clipping")
    bits=job.get("bitDepth",16)
    if bits not in {16,24}:raise SVError("VST3 output supports PCM16/24", "unsupported_format")
    pcm=np.clip(best.T,-1,1-1/(1<<(bits-1)))
    integers=np.rint(pcm*(1<<(bits-1))).astype(np.int32)
    if bits==16:data=integers.astype("<i2").tobytes()
    else:
        b=integers.astype("<i4").view(np.uint8).reshape(-1,4);data=b[:,:3].tobytes()
    target=work/"render.wav"
    with wave.open(str(target),"wb") as f:
        f.setnchannels(channels);f.setsampwidth(bits//8);f.setframerate(sample_rate);f.writeframes(data)
    from .audio import check
    report=check(target,expected_seconds=duration)
    if not report["valid"]:raise SVError(f"Audio failed validation: {report['failures']}","invalid_audio")
    write_json(work/"result.json",report)
    event("complete",audio=str(target),peak=peak)

def main():
    configure_utf8()
    status=0
    try:
        run(read_json(sys.argv[1]))
    except Exception as e:
        event("error",code=getattr(e,"code","render_failed"),message=str(e));status=1
    # Some VST3 plugins leave native background threads alive after rendering.
    # All buffers/files are closed above; terminate only this owned worker.
    sys.stdout.flush();sys.stderr.flush();os._exit(status)

if __name__=="__main__":main()
