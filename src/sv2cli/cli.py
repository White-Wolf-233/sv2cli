import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .errors import SVError
from .io import read_json, write_json
from .project import Project, new_project, difference, QUARTER
from .edit import apply
from .config import profile, doctor, load_config, set_profile, catalog
from .capabilities import CAPABILITIES

def _parser():
    p=argparse.ArgumentParser(prog="sv2cli",description="Synthesizer V Studio 2 project tools and VST3 render CLI")
    p.add_argument("--version",action="version",version=__version__)
    p.add_argument("--profile",default="default",help="Named machine/environment profile")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor");sub.add_parser("capabilities")
    def source(name,help=None):
        s=sub.add_parser(name,help=help);s.add_argument("project");return s
    def write(s):
        s.add_argument("-o","--output",required=True);s.add_argument("--force",action="store_true")
    def tracks(s):s.add_argument("--track",action="append",help="Exact name or one-based #N; repeat for multiple tracks")
    n=sub.add_parser("new");write(n);n.add_argument("--name",default="Track 1");n.add_argument("--bpm",type=float,default=120)
    source("inspect");source("validate")
    s=source("notes");tracks(s);s.add_argument("--start",type=int);s.add_argument("--end",type=int);s.add_argument("-o","--output");s.add_argument("--force",action="store_true")
    s=source("repair");write(s)
    s=source("diff");s.add_argument("other");s.add_argument("--summary",action="store_true")
    s=source("edit", "Apply a transactional JSON operation recipe");write(s);s.add_argument("--recipe",required=True);s.add_argument("--allow-score-changes",action="store_true");s.add_argument("--score-lock",action="store_true");s.add_argument("--dry-run",action="store_true")
    s=source("voice", "Set voice identity or parameters for selected tracks");write(s);tracks(s);s.add_argument("--name");s.add_argument("--language",default="japanese");s.add_argument("--phoneset",default="romaji");s.add_argument("--backend",default="SVR3");s.add_argument("--database-version",default="201");s.add_argument("--language-override");s.add_argument("--inherit",action="store_true");s.add_argument("--clear-dictionary",action="store_true");s.add_argument("--params",help="JSON object or @path.json");s.add_argument("--scope",choices=["main","all"],default="all")
    s=source("mixer");write(s);tracks(s);s.add_argument("--gain",type=float);s.add_argument("--pan",type=float);s.add_argument("--mute",choices=["true","false"]);s.add_argument("--solo",choices=["true","false"])
    v=sub.add_parser("voices");v.add_argument("--name");v.add_argument("--data-root",action="append")
    c=sub.add_parser("config");c.add_argument("action",choices=["show","set"]);c.add_argument("--name",default="default");c.add_argument("--value",help="JSON object or @path.json")
    c=sub.add_parser("convert");c.add_argument("format",choices=["midi-in","midi-out","csv-in","csv-out"]);c.add_argument("source");write(c);c.add_argument("--project");c.add_argument("--track",default="#1");c.add_argument("--ppq",type=int,default=960)
    r=source("render");write(r);tracks(r);r.add_argument("--backend",choices=["vst3","command"],default="vst3");r.add_argument("--stems",action="store_true");r.add_argument("--timeout",type=float,default=1800);r.add_argument("--warmup",type=float,default=15);r.add_argument("--attempts",type=int,default=4);r.add_argument("--tail",type=float,default=2);r.add_argument("--channels",type=int,choices=[1,2],default=2);r.add_argument("--bit-depth",type=int,choices=[16,24],default=16);r.add_argument("--sample-rate",type=int,default=44100);r.add_argument("--single-pass",action="store_true")
    a=sub.add_parser("audio-check");a.add_argument("audio");a.add_argument("--expected-seconds",type=float)
    t=source("time");t.add_argument("--blick",type=int,required=True)
    b=sub.add_parser("batch");b.add_argument("manifest");b.add_argument("--keep-going",action="store_true")
    l=sub.add_parser("live");l.add_argument("action",choices=["install","call"]);l.add_argument("--scripts-dir");l.add_argument("--mailbox");l.add_argument("--session",default="default");l.add_argument("--method",default="host.info");l.add_argument("--args",default="{}");l.add_argument("--timeout",type=float,default=10)
    return p

def _value(text):
    if text is None:return None
    if text.startswith("@"):return read_json(text[1:])
    try:return json.loads(text)
    except ValueError as e:raise SVError(f"Invalid JSON argument: {e}") from e

def _guard_output(source,output):
    if output and Path(source).resolve()==Path(output).resolve():
        raise SVError("Use a new output path; source projects are never overwritten", "source_protected")

def execute(a):
    cmd=a.command
    if cmd=="doctor":return doctor(a.profile)
    if cmd=="capabilities":return {"version":__version__,"capabilities":CAPABILITIES}
    if cmd=="new":return {"output":new_project(a.name,a.bpm).save(a.output,a.force)}
    if cmd=="voices":
        result=catalog(a.data_root or profile(a.profile).get("data_roots",[]))
        if a.name:result["catalog"]=[v for v in result["catalog"] if a.name.casefold() in v["name"].casefold()]
        return result
    if cmd=="config":
        if a.action=="show":return {"config":load_config(),"resolved":profile(a.profile)}
        return {"configPath":set_profile(a.name,_value(a.value))}
    if cmd=="audio-check":
        from .audio import check
        return check(a.audio,a.expected_seconds)
    if cmd=="convert":
        from .convert import midi_import,midi_export,csv_import,csv_export
        if a.format=="midi-in":return {"output":midi_import(a.source,a.output,a.force)}
        if a.format=="midi-out":return {"output":midi_export(Project.load(a.source),a.output,force=a.force,ppq=a.ppq)}
        if a.format=="csv-out":return {"output":csv_export(Project.load(a.source),a.output,[a.track],a.force)}
        if not a.project:raise SVError("csv-in requires --project and --track")
        _guard_output(a.project,a.output)
        return {"output":csv_import(a.source,Project.load(a.project),a.track,a.output,a.force)}
    if cmd=="batch":
        jobs=read_json(a.manifest)
        if not isinstance(jobs,list):raise SVError("Batch manifest must be a JSON array of argv arrays")
        results=[];base=Path(a.manifest).resolve().parent
        # Jobs contain ordinary CLI argv, not executable shell code. Paths use
        # the caller's working directory, just like individual commands.
        for i,args in enumerate(jobs):
            if not isinstance(args,list) or not all(isinstance(v,str) for v in args):raise SVError("Each batch job must be an argv array")
            if "batch" in args:raise SVError("Nested batch jobs are unsupported")
            try:
                ns=_parser().parse_args(args);value=execute(ns)
                if value.get("valid") is False:raise SVError("Job validation failed")
                results.append({"index":i,"ok":True,"result":value})
            except (SVError,SystemExit) as e:
                results.append({"index":i,"ok":False,"error":str(e)})
                if not a.keep_going:break
        return {"valid":all(x["ok"] for x in results),"jobs":results}
    if cmd=="live":
        from .live import install,call
        if a.action=="install":return install(a.scripts_dir,a.mailbox,a.session)
        return call(a.method,_value(a.args),a.mailbox,a.session,a.timeout)
    p=Project.load(a.project)
    if cmd=="inspect":return p.summary()
    if cmd=="validate":return p.validate()
    if cmd=="time":return {"blick":a.blick,"quarters":a.blick/QUARTER,"seconds":p.seconds(a.blick)}
    if cmd=="notes":
        rows=p.notes(a.track)
        if a.start is not None:rows=[r for r in rows if r["onset"]+r["duration"]>a.start]
        if a.end is not None:rows=[r for r in rows if r["onset"]<a.end]
        return {"output":write_json(a.output,rows,a.force),"notes":len(rows)} if a.output else {"notes":rows}
    if cmd=="diff":
        report=difference(p,Project.load(a.other))
        if a.summary:report.pop("changes")
        return report
    _guard_output(a.project,a.output)
    if cmd=="repair":
        q=p.copy();report=q.repair()
        if not report["validation"]["valid"]:raise SVError(f"Conservative repair cannot fix: {report['validation']['issues']}","invalid_project")
        report["output"]=q.save(a.output,a.force);return report
    if cmd=="render":
        from .render import render
        return render(a.project,a.output,a.profile,a.backend,a.track,a.stems,a.timeout,a.warmup,a.attempts,a.tail,a.force,a.channels,a.bit_depth,a.sample_rate,a.single_pass)
    if cmd=="edit":
        operations=read_json(a.recipe);q=apply(p,operations,a.allow_score_changes,a.score_lock)
        report=difference(p,q)
        if not a.dry_run:report["output"]=q.save(a.output,a.force)
        else:report["dryRun"]=True
        return report
    if cmd=="voice":
        ops=[]
        if a.name:
            db={"name":a.name,"language":a.language,"phoneset":a.phoneset,"backendType":a.backend,"version":a.database_version,"languageOverride":"","phonesetOverride":""}
            ops.append({"op":"voice.switch","tracks":a.track,"database":db,"inherit":a.inherit,"clearDictionary":a.clear_dictionary})
        if a.params:ops.append({"op":"voice.set","tracks":a.track,"values":_value(a.params),"scope":a.scope})
        if a.language_override is not None:ops.append({"op":"language.set","tracks":a.track,"language":a.language_override})
        if not ops:raise SVError("Specify --name, --params or --language-override")
    elif cmd=="mixer":
        values={k:v for k,v in {"gainDecibel":a.gain,"pan":a.pan,"mute":None if a.mute is None else a.mute=="true","solo":None if a.solo is None else a.solo=="true"}.items() if v is not None}
        if not values:raise SVError("Specify a mixer value")
        ops=[{"op":"mixer.set","tracks":a.track,"values":values}]
    else:raise SVError(f"Unsupported command {cmd}")
    q=apply(p,ops,score_lock=True)
    return {"output":q.save(a.output,a.force),"scoreAndTimingIdentical":True}

def main(argv=None):
    try:
        result=execute(_parser().parse_args(argv))
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0 if result.get("valid",True) else 2
    except SVError as e:
        print(json.dumps({"error":{"code":e.code,"message":str(e)}},ensure_ascii=False),file=sys.stderr);return 2
    except (ValueError,KeyError,TypeError,OSError,OverflowError) as e:
        print(json.dumps({"error":{"code":"invalid_input","message":str(e)}},ensure_ascii=False),file=sys.stderr);return 2
    except KeyboardInterrupt:
        print('{"error":{"code":"cancelled","message":"Cancelled"}}',file=sys.stderr);return 130
