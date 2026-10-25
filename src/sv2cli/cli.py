import argparse
import json
from pathlib import Path
import sys
from . import __version__
from .errors import SVError
from .io import read_json, write_json,configure_utf8, backup_file
from .project import Project, new_project, difference, QUARTER
from .edit import apply
from .config import profile, doctor, load_config, set_profile, catalog
from .capabilities import CAPABILITIES

def _parser():
    p=argparse.ArgumentParser(prog="sv2cli",description="Synthesizer V Studio 2 project tools and VST3 render CLI")
    p.add_argument("--version",action="version",version=__version__)
    p.add_argument("--profile",default="default",help="Named machine/environment profile")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor");sub.add_parser("capabilities");sub.add_parser('recipe-schema');sub.add_parser('lyrics-plan-schema',help='Describe the independent lyric-plan format and show a non-reviewed example')
    status=sub.add_parser('job-status');status.add_argument('path',help='Stem directory, WAV path or manifest JSON')
    def source(name,help=None):
        s=sub.add_parser(name,help=help);s.add_argument("project");return s
    def write(s, in_place=False):
        if in_place:
            g=s.add_mutually_exclusive_group(required=True)
            g.add_argument('-o','--output');g.add_argument('--in-place',action='store_true',help='Atomically replace the input SVP, keeping a timestamped backup')
        else:s.add_argument("-o","--output",required=True)
        s.add_argument("--force",action="store_true")
    def tracks(s):s.add_argument("--track",action="append",help="Exact name or one-based #N; repeat for multiple tracks")
    n=sub.add_parser("new");write(n);n.add_argument("--name",default="Track 1");n.add_argument("--bpm",type=float,default=120)
    source("inspect");source("validate")
    s=source("preflight");tracks(s);s.add_argument("-o","--output");s.add_argument("--force",action="store_true")
    s=source('lyrics-check', 'Compare lyric text and exact syllable underlay against an independent plan')
    s.add_argument('--plan',required=True,help='JSON plan; see lyrics-plan-schema. Times are absolute quarter beats.');s.add_argument('--text-only',action='store_true',help='Diagnose phrase text without claiming per-note mapping')
    s.add_argument('--require-full-project',action='store_true');s.add_argument('-o','--output');s.add_argument('--force',action='store_true')
    s=source("notes");tracks(s);s.add_argument("--start");s.add_argument("--end");s.add_argument("-o","--output");s.add_argument("--force",action="store_true")
    s=source('groups');tracks(s)
    s=source("repair");write(s,True)
    s=source("diff");s.add_argument("other");s.add_argument("--summary",action="store_true")
    s=source("edit", "Apply a transactional JSON operation recipe");write(s,True);s.add_argument("--recipe",required=True);s.add_argument("--allow-score-changes",action="store_true");s.add_argument("--score-lock",action="store_true");s.add_argument("--dry-run",action="store_true")
    s=source("voice", "Set voice identity or parameters for selected tracks");write(s,True);tracks(s);s.add_argument("--name");s.add_argument("--language",default="japanese");s.add_argument("--phoneset",default="romaji");s.add_argument("--backend",default="SVR3");s.add_argument("--database-version",default="201");s.add_argument("--language-override");s.add_argument("--override-phoneset");s.add_argument("--inherit",action="store_true");s.add_argument("--clear-dictionary",action="store_true");s.add_argument("--params",help="JSON object or @path.json");s.add_argument("--scope",choices=["main","all"],default="all");s.add_argument('--dry-run',action='store_true')
    s=source("mixer");write(s,True);tracks(s);s.add_argument("--gain",type=float);s.add_argument("--pan",type=float);s.add_argument("--mute",choices=["true","false"]);s.add_argument("--solo",choices=["true","false"]);s.add_argument('--dry-run',action='store_true')
    v=sub.add_parser("voices");v.add_argument("--name");v.add_argument("--data-root",action="append")
    c=sub.add_parser("config");c.add_argument("action",choices=["show","set"]);c.add_argument("--name",default="default");c.add_argument("--value",help="JSON object or @path.json")
    c=sub.add_parser("convert");c.add_argument("format",choices=["midi-in","midi-out","csv-in","csv-out"]);c.add_argument("source");write(c);c.add_argument("--project");c.add_argument("--track");c.add_argument("--ppq",type=int,default=960)
    c.add_argument('--truncate-overlaps',action='store_true',help='Explicitly truncate earlier same-pitch notes at the next onset; FIFO note-offs; report changes')
    pg=c.add_mutually_exclusive_group();pg.add_argument('--polyphony',choices=['preserve','reject','split','top'],default='preserve')
    pg.add_argument('--top-voice',dest='polyphony',action='store_const',const='top',help='Explicitly discard lower simultaneous pitches')
    pg.add_argument('--monophonic',dest='polyphony',action='store_const',const='reject',help='Reject polyphonic input')
    c.add_argument('--lyric-default',default='la',help='Default only for notes without a MIDI lyric event')
    c.add_argument('--midi-charset',default='utf8',help='MIDI text encoding, e.g. utf8 or latin1')
    r=source("render");write(r);tracks(r)
    r.add_argument("--backend",choices=["vst3","command"],default="vst3")
    r.add_argument("--stems",action="store_true");r.add_argument("--timeout",type=float,default=1800)
    r.add_argument("--warmup",type=float,default=15)
    r.add_argument("--attempts",type=int,choices=[1],default=1,help='One pass only; automatic retries are disabled')
    r.add_argument("--tail",type=float,default=2);r.add_argument("--channels",type=int,choices=[1,2],default=2)
    r.add_argument("--bit-depth",type=int,choices=[16,24],default=16);r.add_argument("--sample-rate",type=int,default=44100)
    r.add_argument("--single-pass",action="store_true",help='Deprecated compatibility flag: all renders use one pass')
    r.add_argument('--lyrics-plan',help='Reject incomplete, unreviewed or mismatched full-project lyric plans before loading the plugin')
    a=sub.add_parser("audio-check");a.add_argument("audio");a.add_argument("--expected-seconds",type=float)
    a=sub.add_parser('audio-normalize');a.add_argument('audio');write(a);a.add_argument('--target-peak',type=float,default=-1,help='Sample peak in dBFS, default -1')
    a=source('coverage-check');a.add_argument('audio');tracks(a);a.add_argument('-o','--output');a.add_argument('--force',action='store_true')
    a.add_argument('--silence-dbfs',type=float,default=-80);a.add_argument('--max-silent-seconds',type=float,default=.5)
    ng=r.add_mutually_exclusive_group();ng.add_argument('--normalize',dest='target_peak',action='store_const',const=-1)
    ng.add_argument('--target-peak',dest='target_peak',type=float,help='Explicit sample-peak normalization in dBFS')
    r.add_argument('--silence-dbfs',type=float,default=-80);r.add_argument('--max-silent-seconds',type=float,default=.5)
    t=source('tune');write(t,True);tracks(t);t.add_argument('--mode',choices=['rigid','default','flat'],required=True)
    t.add_argument('--start');t.add_argument('--end');t.add_argument('--transition-ms',type=float,default=10)
    t.add_argument('--replace-controls',action='store_true');t.add_argument('--vibrato',type=float);t.add_argument('--dry-run',action='store_true')
    t=source('effects');write(t,True);tracks(t);t.add_argument('--params',required=True,help='JSON object or @path.json');t.add_argument('--dry-run',action='store_true')
    r.add_argument('--resume',action='store_true',help='Reuse verified completed renders from a matching manifest')
    r.add_argument('--entry-policy',choices=['check','align','report'],help='Native default: check first isolated waveform entry; align explicitly translates the recording; report permits unchecked mixes')
    r.add_argument('--entry-tolerance',type=float,default=.03,help='First waveform entry tolerance in seconds (default: 0.03)')
    r.add_argument('--entry-landmark',choices=['broadband','voiced'],default='broadband',help='Explicit acoustic landmark; voiced uses a low-band energy proxy and retains broadband evidence')
    t=source("time");g=t.add_mutually_exclusive_group(required=True);g.add_argument("--blick",type=int);g.add_argument('--at',help='b:BLICKS, q:QUARTERS, s:SECONDS, bar:N:BEAT')
    t=source('timing-check');t.add_argument('audio');tracks(t);t.add_argument('--audio-origin',type=float,default=0);t.add_argument('--search',type=float,default=.35);t.add_argument('--tolerance',type=float,default=.12);t.add_argument('-o','--output');t.add_argument('--force',action='store_true')
    t=source('audio-shift');t.add_argument('audio');tracks(t);t.add_argument('--seconds',type=float,required=True);t.add_argument('--audio-origin',type=float,default=0);write(t)
    t=source('wave-align');t.add_argument('audio');tracks(t);write(t);t.add_argument('--scope',choices=['track','phrase'],default='track');t.add_argument('--gap',type=float,default=.35);t.add_argument('--search',type=float,default=.7);t.add_argument('--threshold',type=float,default=.12);t.add_argument('--tolerance',type=float,default=.008);t.add_argument('--audio-origin',type=float,default=0)
    timing_parser=sub.choices['timing-check'];timing_parser.add_argument('--start');timing_parser.add_argument('--end')
    sub.choices['wave-align'].add_argument('--landmark',choices=['broadband','voiced'],default='broadband')
    t=source('entry-check');t.add_argument('audio');tracks(t)
    t.add_argument('--landmark',choices=['broadband','voiced'],default='broadband')
    t.add_argument('--tolerance',type=float,default=.03);t.add_argument('-o','--output');t.add_argument('--force',action='store_true')
    b=sub.add_parser("batch");b.add_argument("manifest");b.add_argument("--keep-going",action="store_true")
    l=sub.add_parser("live");l.add_argument("action",choices=["install","call"]);l.add_argument("--scripts-dir");l.add_argument("--mailbox");l.add_argument("--session",default="default");l.add_argument("--method",default="host.info");l.add_argument("--args",default="{}");l.add_argument("--timeout",type=float,default=10)
    return p

def _value(text):
    if text is None:return None
    if text.startswith("@"):return read_json(text[1:])
    try:return json.loads(text)
    except ValueError as e:raise SVError(f"Invalid JSON argument: {e}") from e

def _guard_output(source,output,allow=False):
    if output and Path(source).resolve()==Path(output).resolve() and not allow:
        raise SVError("Use a new output path, or an editing command with --in-place / -o SOURCE --force", "source_protected")

def _save(p,a):
    if Path(a.project).resolve()==Path(a.output).resolve():
        old=getattr(a,'_source_bytes',None)
        if old is None or Path(a.project).read_bytes()!=old:
            raise SVError('Source changed during the edit; reload before overwriting','source_changed')
        backup=backup_file(a.project)
        return {'output':p.save(a.output,True),'backup':backup,'inPlace':True}
    return {'output':p.save(a.output,a.force)}

def execute(a):
    cmd=a.command
    editing=cmd in {'repair','edit','voice','mixer','tune','effects'}
    if getattr(a,'in_place',False):a.output=a.project;a.force=True
    if getattr(a,"output",None):
        for key in ("project","source","recipe","plan","lyrics_plan"):
            value=getattr(a,key,None)
            if value:_guard_output(value,a.output,editing and key=='project' and a.force)
        if getattr(a,'audio',None):_guard_output(a.audio,a.output)
    if cmd=="doctor":return doctor(a.profile)
    if cmd=="capabilities":return {"version":__version__,"capabilities":CAPABILITIES}
    if cmd=='recipe-schema':
        from .recipe import schema
        return schema()
    if cmd=='lyrics-plan-schema':
        from .lyrics import schema
        return schema()
    if cmd=='job-status':
        from .render import job_status
        return job_status(a.path)
    if cmd=="new":return {"output":new_project(a.name,a.bpm).save(a.output,a.force)}
    if cmd=="voices":
        result=catalog(a.data_root or profile(a.profile).get("data_roots",[]))
        if a.name:result["catalog"]=[v for v in result["catalog"] if a.name.casefold() in v["name"].casefold()]
        return result
    if cmd=="config":
        if a.action=="show":return {"config":load_config(),"resolved":profile(a.profile)}
        return {"configPath":set_profile(a.name,_value(a.value))}
    if cmd=='audio-normalize':
        from .normalize import write as normalize
        return normalize(a.audio,a.output,a.target_peak,a.force)
    if cmd=="audio-check":
        from .audio import check
        return check(a.audio,a.expected_seconds)
    if cmd=="convert":
        from .convert import midi_import,midi_export,csv_import,csv_export
        if a.format=="midi-in":
            report={}
            out=midi_import(a.source,a.output,a.force,truncate_overlaps=a.truncate_overlaps,polyphony=a.polyphony,
                            lyric_default=a.lyric_default,charset=a.midi_charset,report=report)
            return {"output":out,"conversion":report}
        if a.format=="midi-out":return {"output":midi_export(Project.load(a.source),a.output,[a.track] if a.track else None,force=a.force,ppq=a.ppq)}
        if a.format=="csv-out":return {"output":csv_export(Project.load(a.source),a.output,[a.track or '#1'],a.force)}
        if not a.project:raise SVError("csv-in requires --project and --track")
        _guard_output(a.project,a.output)
        return {"output":csv_import(a.source,Project.load(a.project),a.track or '#1',a.output,a.force)}
    if cmd=="batch":
        jobs=read_json(a.manifest)
        if not isinstance(jobs,list):raise SVError("Batch manifest must be a JSON array of argv arrays")
        results=[];base=Path(a.manifest).resolve().parent
        # Jobs contain ordinary CLI argv, not executable shell code. Paths use
        # the caller's working directory, just like individual commands.
        for i,args in enumerate(jobs):
            if not isinstance(args,list) or not all(isinstance(v,str) for v in args):raise SVError("Each batch job must be an argv array")
            try:
                ns=_parser().parse_args(args)
                if ns.command=='batch':raise SVError('Nested batch jobs are unsupported')
                if not any(v=='--profile' or v.startswith('--profile=') for v in args):ns.profile=a.profile
                value=execute(ns)
                if value.get("valid") is False:raise SVError("Job validation failed")
                results.append({"index":i,"ok":True,"result":value})
            except (SVError,SystemExit,ValueError,KeyError,TypeError,OSError,OverflowError) as e:
                results.append({"index":i,"ok":False,"error":str(e),'code':getattr(e,'code','invalid_input')})
                if not a.keep_going:break
        return {"valid":all(x["ok"] for x in results),"jobs":results}
    if cmd=="live":
        from .live import install,call
        if a.action=="install":return install(a.scripts_dir,a.mailbox,a.session)
        return call(a.method,_value(a.args),a.mailbox,a.session,a.timeout)
    if editing:a._source_bytes=Path(a.project).read_bytes()
    p=Project.load(a.project)
    from .timing import describe,position
    if cmd=="inspect":return p.summary()
    if cmd=="validate":return p.validate()
    if cmd=='lyrics-check':
        from .lyrics import audit
        import hashlib
        if not p.validate()['valid']:raise SVError('Invalid project; run validate first','invalid_project')
        report=audit(p.data,read_json(a.plan),a.text_only,a.require_full_project)
        report.update(valid=report['planMatches'],projectSHA256=hashlib.sha256(Path(a.project).read_bytes()).hexdigest(),
                      planSHA256=hashlib.sha256(Path(a.plan).read_bytes()).hexdigest())
        if a.output:write_json(a.output,report,a.force)
        return report
    if cmd=='preflight':
        from .preflight import check
        report=check(p,a.track)
        if a.output:write_json(a.output,report,a.force)
        return report
    if cmd=='coverage-check':
        from .coverage import check
        from .timing import read_pcm
        audio,rate,_=read_pcm(a.audio)
        report=check(p,audio,rate,a.track,a.silence_dbfs,a.max_silent_seconds)
        if a.output:write_json(a.output,report,a.force)
        return report
    if cmd=="time":return describe(p,a.blick if a.blick is not None else a.at)
    if cmd=='groups':
        from .timing import groups
        return {'groups':groups(p,a.track)}
    if cmd=='wave-align':
        from .wave_align import write as align_write
        return align_write(p,a.audio,a.output,a.track,a.force,gap=a.gap,search=a.search,threshold=a.threshold,tolerance=a.tolerance,origin=a.audio_origin,scope=a.scope,landmark=a.landmark)
    if cmd=='entry-check':
        from .wave_align import entries
        from .timing import read_pcm
        from .project import finite
        finite(a.tolerance,'entry tolerance')
        if a.tolerance<.002:raise SVError('Entry tolerance must be at least 2 ms')
        audio,rate,_=read_pcm(a.audio);rows=entries(p,audio,rate,a.track,landmark=a.landmark)
        report={'valid':rows[0]['observed'] is not None and abs(rows[0]['delta'])<=a.tolerance,
                'landmark':a.landmark,'toleranceSeconds':a.tolerance,'entries':rows,
                'scoreFingerprint':p.score_fingerprint(),'audioTranslated':False,
                'allNoteOnsetsVerified':False,'phonemeAlignmentVerified':False}
        if a.landmark!='broadband':report['broadbandEntries']=entries(p,audio,rate,a.track)
        if a.output:write_json(a.output,report,a.force)
        return report
    if cmd in {'timing-check','audio-shift'}:
        from .timing import check,read_pcm,shift
        if cmd=='audio-shift':return shift(p,a.audio,a.output,a.track,a.seconds,a.force,a.audio_origin)
        audio,rate,_=read_pcm(a.audio)
        report=check(p,audio,rate,a.track,a.audio_origin,a.search,a.tolerance,a.start,a.end)
        if a.output:write_json(a.output,report,a.force)
        return report
    if cmd=="notes":
        rows=p.notes(a.track)
        if a.start is not None:rows=[r for r in rows if r["onset"]+r["duration"]>position(p,a.start)]
        if a.end is not None:rows=[r for r in rows if r["onset"]<position(p,a.end)]
        return {"output":write_json(a.output,rows,a.force),"notes":len(rows)} if a.output else {"notes":rows}
    if cmd=="diff":
        report=difference(p,Project.load(a.other))
        if a.summary:report.pop("changes")
        return report
    _guard_output(a.project,a.output,editing and a.force)
    if cmd=="repair":
        q=p.copy();report=q.repair()
        if not report["validation"]["valid"]:raise SVError(f"Conservative repair cannot fix: {report['validation']['issues']}","invalid_project")
        report.update(_save(q,a));return report
    if cmd=="render":
        lyric_report=None
        if a.lyrics_plan:
            from .lyrics import audit
            import hashlib
            lyric_report=audit(p.data,read_json(a.lyrics_plan),require_full=True)
            if not lyric_report['planMatches'] or not lyric_report['sourceReviewDeclared']:
                raise SVError('Lyric plan is incomplete, mismatched or not declared reviewed; run lyrics-check --require-full-project for details','lyric_plan_mismatch')
            lyric_report.update(projectSHA256=hashlib.sha256(Path(a.project).read_bytes()).hexdigest(),
                                planSHA256=hashlib.sha256(Path(a.lyrics_plan).read_bytes()).hexdigest())
        from .render import render
        result=render(a.project,a.output,a.profile,a.backend,a.track,a.stems,a.timeout,a.warmup,a.attempts,a.tail,a.force,a.channels,a.bit_depth,a.sample_rate,a.single_pass,resume=a.resume,entry_policy=a.entry_policy,entry_tolerance=a.entry_tolerance,entry_landmark=a.entry_landmark,target_peak=a.target_peak,silence_dbfs=a.silence_dbfs,max_silent_seconds=a.max_silent_seconds)
        if lyric_report is not None:result['lyricPlanVerification']=lyric_report
        return result
    if cmd=="edit":
        operations=read_json(a.recipe);q=apply(p,operations,a.allow_score_changes,a.score_lock)
        report=difference(p,q)
        report['operations']=q.edit_report
        if not a.dry_run:report.update(_save(q,a))
        else:report["dryRun"]=True
        return report
    if cmd=='tune':
        base={'tracks':a.track}
        if a.start is not None:base['start']=a.start
        if a.end is not None:base['end']=a.end
        ops=[dict(base,op='notes.expression',preset='rigid' if a.mode=='flat' else a.mode)]
        if a.vibrato is not None:ops[0]['vibrato']=a.vibrato
        if a.mode=='flat':ops.append(dict(base,op='pitch.flatten',transitionMs=a.transition_ms,replaceControls=a.replace_controls))
    elif cmd=='effects':ops=[{'op':'effects.set','tracks':a.track,'values':_value(a.params)}]
    elif cmd=="voice":
        ops=[]
        if a.name:
            db={"name":a.name,"language":a.language,"phoneset":a.phoneset,"backendType":a.backend,"version":a.database_version,"languageOverride":"","phonesetOverride":""}
            ops.append({"op":"voice.switch","tracks":a.track,"database":db,"inherit":a.inherit,"clearDictionary":a.clear_dictionary})
        if a.params:ops.append({"op":"voice.set","tracks":a.track,"values":_value(a.params),"scope":a.scope})
        if a.language_override is not None:
            op={"op":"language.set","tracks":a.track,"language":a.language_override}
            if a.override_phoneset is not None:op["phoneset"]=a.override_phoneset
            ops.append(op)
        if not ops:raise SVError("Specify --name, --params or --language-override")
    elif cmd=="mixer":
        values={k:v for k,v in {"gainDecibel":a.gain,"pan":a.pan,"mute":None if a.mute is None else a.mute=="true","solo":None if a.solo is None else a.solo=="true"}.items() if v is not None}
        if not values:raise SVError("Specify a mixer value")
        ops=[{"op":"mixer.set","tracks":a.track,"values":values}]
    else:raise SVError(f"Unsupported command {cmd}")
    q=apply(p,ops,score_lock=True)
    report=difference(p,q)
    report['operations']=q.edit_report
    if a.dry_run:report['dryRun']=True
    else:report.update(_save(q,a))
    return report

def main(argv=None):
    configure_utf8()
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
