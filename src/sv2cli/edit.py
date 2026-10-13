"""Transactional editing with explicit score changes and shared-group isolation."""
from copy import deepcopy
import time
import uuid
from .errors import SVError
from .project import QUARTER, PARAMETERS, VOICE_RANGES, empty_group, empty_ref, empty_track, guid, integer, finite, numeric

SCORE_OPS = {"notes.replace", "notes.update", "notes.transpose", "notes.shift", "track.add", "track.remove", "track.clone", "tempo.set", "meter.set", "group.shift", "group.transpose", "group.remove", "lyrics.set", "phonemes.set"}
VOICE_KEYS = set(VOICE_RANGES)|{"vocalModeInherited", "vocalModePreset", "vocalModeParams", "tF0VbrStart", "fF0Vbr", "dF0Vbr", "pF0Vbr", "tF0VbrLeft", "tF0VbrRight", "paramConsonantStrength", "paramMouthOpening", "choirPitchDeviation", "choirTimingDeviation", "choirLoudnessDeviation"}

def _notes(project, selectors, groups=None):
    project.isolate_groups(selectors)
    seen = set()
    for _, t in project.tracks(selectors):
        for ref, group in project.references(t):
            if groups and group.get("uuid") not in groups and group.get("name") not in groups:
                continue
            if group["uuid"] not in seen:
                seen.add(group["uuid"])
                yield ref, group

def _new_note(row, offset=0, pitch_offset=0):
    n = deepcopy(row)
    for k in ["track", "trackName", "group", "groupID", "note", "muted"]:
        n.pop(k, None)
    n["onset"] = integer(n["onset"], "onset")-offset
    n["duration"] = integer(n["duration"], "duration")
    if n["duration"] <= 0:
        raise SVError("Note duration must be positive")
    n["pitch"] = integer(n["pitch"], "pitch")-pitch_offset
    numeric(n["pitch"], "pitch", 0, 127)
    n["uuid"] = uuid.uuid4().hex[:16]
    n.setdefault("musicalType", "singing")
    n.setdefault("lyrics", "la")
    n.setdefault("phonemes", "")
    n.setdefault("attributes", {})
    return n

def _set_voice(project, op):
    values = op.get("values", {})
    if not isinstance(values, dict):
        raise SVError("voice values must be an object")
    unknown = set(values)-VOICE_KEYS
    if unknown:
        raise SVError(f"Unknown voice parameter(s): {sorted(unknown)}")
    for key, value in values.items():
        if key in VOICE_RANGES:
            numeric(value, key, *VOICE_RANGES[key])
            if key == "choirNumStems":
                integer(value, key)
    for _, t in project.tracks(op.get("tracks")):
        refs = [r for r,_ in project.references(t)]
        if op.get("scope", "all") == "main":
            refs = refs[:1]
        for ref in refs:
            ref.setdefault("voice", {}).update(deepcopy(values))
            if values.get("vocalModeInherited") is False:
                ref["voice"].setdefault("vocalModeParams", {})
            ref["timestampLMR"] = round(time.time()*1000)
            ref["timestampLRSR"] = 0

def apply(project, operations, allow_score_changes=False, score_lock=False):
    if not isinstance(operations, list) or not all(isinstance(o,dict) for o in operations):
        raise SVError("Recipe must be an array of operation objects")
    result = project.copy()
    before = project.score_fingerprint()
    for op in operations:
        name = op.get("op")
        if name in SCORE_OPS and not allow_score_changes:
            raise SVError(f"{name} changes the score; pass --allow-score-changes explicitly", "score_locked")
        selectors = op.get("tracks")
        if name == "voice.set":
            _set_voice(result, op)
        elif name == "voice.switch":
            db = op.get("database")
            if not isinstance(db,dict) or not db.get("name") or not db.get("backendType"):
                raise SVError("voice.switch needs database.name and database.backendType")
            for _, t in result.tracks(selectors):
                refs = [r for r,_ in result.references(t)]
                refs[0]["database"] = deepcopy(db)
                # Clearing group overrides to inherit avoids hidden stale singers.
                for ref in refs[1:]:
                    ref["database"] = {"name":"", "language":"", "phoneset":"", "languageOverride":"", "phonesetOverride":"", "backendType":"", "version":"-2"} if op.get("inherit", False) else deepcopy(db)
                if op.get("clearDictionary", False):
                    for ref in refs:
                        ref["dictionary"] = ""
        elif name == "language.set":
            language=op.get("language")
            if language not in {"", "mandarin", "japanese", "english", "spanish", "cantonese", "korean"}:
                raise SVError("Unknown language override")
            for _,t in result.tracks(selectors):
                for r,_ in result.references(t):
                    r.setdefault("database", {})["languageOverride"] = language
                    if "phoneset" in op:
                        r["database"]["phonesetOverride"] = op["phoneset"]
        elif name == "dictionary.set":
            if not isinstance(op.get("dictionary"),str):raise SVError("dictionary must be a string")
            for _,t in result.tracks(selectors):
                for r,_ in result.references(t):r["dictionary"]=op["dictionary"]
        elif name == "mixer.set":
            values=op.get("values", {})
            if set(values)-{"gainDecibel", "pan", "mute", "solo", "display"}:
                raise SVError("Unknown mixer field")
            if "pan" in values:
                numeric(values["pan"], "pan", -1, 1)
            if "gainDecibel" in values:
                numeric(values["gainDecibel"], "gainDecibel", -96, 24)
            for k in {"mute", "solo", "display"}&values.keys():
                if not isinstance(values[k],bool):
                    raise SVError(f"{k} must be boolean")
            for _,t in result.tracks(selectors):
                t.setdefault("mixer", {}).update(deepcopy(values))
        elif name == "effects.set":
            values=op.get("values", {})
            if set(values)-{"room", "postRoomEq", "compressor", "reverb"}:
                raise SVError("Unknown effect; use room, postRoomEq, compressor, reverb")
            for _,t in result.tracks(selectors):
                fx=t.setdefault("mixer", {}).setdefault("fxParams", {})
                for k,v in values.items():
                    if not isinstance(v,dict):
                        raise SVError("Effect settings must be objects")
                    fx.setdefault(k,{}).update(deepcopy(v))
        elif name == "track.rename":
            selected=result.tracks(selectors)
            if len(selected)!=1 or not op.get("name"):
                raise SVError("Rename selects exactly one track and requires a name")
            selected[0][1]["name"]=op["name"]
        elif name == "track.set":
            values=op.get("values", {})
            if set(values)-{"dispColor", "dispOrder", "renderEnabled"}:
                raise SVError("track.set accepts dispColor, dispOrder, renderEnabled")
            for _,t in result.tracks(selectors):
                t.update(deepcopy(values))
        elif name == "track.add":
            t=empty_track(op.get("name", "New Track"));t["dispOrder"]=len(result.data["tracks"])
            result.data["tracks"].append(t)
        elif name == "track.remove":
            if not selectors:
                raise SVError("Track removal requires explicit tracks")
            indices={i for i,_ in result.tracks(selectors)}
            result.data["tracks"]=[t for i,t in result.tracks() if i not in indices]
        elif name == "track.clone":
            selected=result.tracks(selectors)
            if len(selected)!=1:
                raise SVError("Clone selects exactly one track")
            t=deepcopy(selected[0][1]);t["name"]=op.get("name",t["name"]+" copy")
            t["mainGroup"]["uuid"]=guid();t["mainRef"]["uuid"]=guid();t["mainRef"]["groupID"]=t["mainGroup"]["uuid"]
            lib={g["uuid"]:g for g in result.data.get("library",[])}
            for ref in t.get("groups",[]):
                g=deepcopy(lib[ref["groupID"]]);g["uuid"]=guid();result.data["library"].append(g)
                ref["uuid"]=guid();ref["groupID"]=g["uuid"]
            t["dispOrder"]=len(result.data["tracks"]);result.data["tracks"].append(t)
        elif name == "notes.replace":
            selected=result.tracks(selectors)
            if len(selected)!=1:
                raise SVError("notes.replace selects exactly one track")
            t=selected[0][1]
            rows=op.get("notes", [])
            if not isinstance(rows,list):
                raise SVError("notes must be an array")
            t["groups"]=[]
            t["mainGroup"]["notes"]=[_new_note(r) for r in rows]
            t["mainRef"]["blickOffset"]=0;t["mainRef"]["pitchOffset"]=0
        elif name in {"notes.update", "notes.transpose", "notes.shift", "lyrics.set", "phonemes.set"}:
            notes=[]
            for ref,g in _notes(result,selectors,op.get("groups")):
                for n in g.get("notes",[]):
                    if op.get("uuids") and n.get("uuid") not in op["uuids"]:
                        continue
                    if "start" in op and n["onset"]+ref.get("blickOffset",0)<op["start"]:
                        continue
                    if "end" in op and n["onset"]+ref.get("blickOffset",0)>=op["end"]:
                        continue
                    notes.append(n)
            if name in {"lyrics.set", "phonemes.set"}:
                field="lyrics" if name=="lyrics.set" else "phonemes"
                words=op.get("values")
                if not isinstance(words,list) or len(words)!=len(notes):
                    raise SVError(f"Expected exactly {len(notes)} {field} values")
                for n,w in zip(notes,words):
                    if not isinstance(w,str):raise SVError("Lyrics/phonemes must be strings")
                    n[field]=w
            else:
                for n in notes:
                    if name == "notes.transpose":
                        n["pitch"]+=integer(op["semitones"],"semitones")
                        numeric(n["pitch"],"pitch",0,127)
                    elif name=="notes.shift":
                        n["onset"]+=integer(op["blick"],"blick")
                    else:
                        values=deepcopy(op.get("values",{}))
                        if set(values)-{"onset","duration","pitch","lyrics","phonemes","musicalType","detune","accent","attributes","languageOverride"}:
                            raise SVError("Unknown note field")
                        if "attributes" in values:
                            n.setdefault("attributes",{}).update(values.pop("attributes"))
                        n.update(values)
        elif name in {"group.shift", "group.transpose", "group.remove"}:
            for _,t in result.tracks(selectors):
                refs=[r for r,g in result.references(t) if not op.get("groups") or g.get("uuid") in op["groups"] or g.get("name") in op["groups"]]
                if name=="group.remove":
                    if not op.get("groups"):raise SVError("group.remove requires groups")
                    t["groups"]=[r for r in t.get("groups",[]) if r not in refs]
                else:
                    for r in refs:
                        if name=="group.shift":r["blickOffset"]+=integer(op["blick"],"blick")
                        else:r["pitchOffset"]=r.get("pitchOffset",0)+integer(op["semitones"],"semitones")
        elif name == "automation.set":
            param=op.get("parameter")
            if param not in PARAMETERS:raise SVError(f"Unknown automation parameter {param}")
            points=op.get("points", [])
            if not isinstance(points,list):raise SVError("points must be an array")
            for pair in points:
                if not isinstance(pair,list) or len(pair)!=2:raise SVError("Expected [blick, value]")
                integer(pair[0],"point position");finite(pair[1],"point value")
            if len({p[0] for p in points})!=len(points):raise SVError("Duplicate automation position")
            if op.get("mode","cubic") not in {"cubic","linear","cosine"}:raise SVError("Unknown interpolation mode")
            for _,g in _notes(result,selectors,op.get("groups")):
                g.setdefault("parameters",{})[param]={"mode":op.get("mode","cubic"),"points":[v for pair in sorted(points) for v in pair]}
        elif name == "pitch.controls":
            controls=op.get("controls")
            if not isinstance(controls,list):raise SVError("controls must be an array")
            for _,g in _notes(result,selectors,op.get("groups")):
                g["pitchControls"]=deepcopy(controls)
        elif name == "retake.activate":
            take_id=integer(op["id"],"take id")
            for _,g in _notes(result,selectors,op.get("groups")):
                for n in g.get("notes",[]):
                    if op.get("uuids") and n.get("uuid") not in op["uuids"]:continue
                    takes=n.get("takes",{})
                    if take_id not in {x["id"] for x in takes.get("takes",[])}:
                        raise SVError(f"Take {take_id} does not exist for note {n.get('uuid')}")
                    takes["activeTakeId"]=take_id
        elif name == "tempo.set":
            marks=deepcopy(op.get("marks"))
            if not isinstance(marks,list):raise SVError("tempo marks must be an array")
            result.data.setdefault("time",{})["tempo"]=sorted(marks,key=lambda x:x["position"])
        elif name == "meter.set":
            marks=deepcopy(op.get("marks"))
            if not isinstance(marks,list) or not marks or marks[0].get("index")!=0:raise SVError("Meter marks must start at bar index 0")
            for m in marks:
                integer(m["index"],"bar index");numeric(m["numerator"],"numerator",1,64)
                if m["denominator"] not in {1,2,4,8,16,32,64}:raise SVError("Invalid meter denominator")
            result.data.setdefault("time",{})["meter"]=sorted(marks,key=lambda x:x["index"])
        elif name == "render.configure":
            values=op.get("values",{})
            known={"destination","filename","numChannels","bitDepth","sampleRate","aspirationFormat","exportMixDown","exportPitch","bypassGain","bypassPan","bypassEffects"}
            if set(values)-known:raise SVError("Unknown render configuration field")
            if "numChannels" in values and values["numChannels"] not in {1,2}:raise SVError("Channels must be 1 or 2")
            if "bitDepth" in values and values["bitDepth"] not in {16,24,32}:raise SVError("Bit depth must be 16, 24 or 32")
            result.data.setdefault("renderConfig",{}).update(deepcopy(values))
        elif name == "json.patch":
            from .json_patch import patch
            patch(result.data,op.get("patch"))
        else:
            raise SVError(f"Unknown operation: {name}", "unsupported_operation")
    result.update_ranges()
    validation=result.validate()
    if not validation["valid"]:
        raise SVError(f"Edited project is invalid: {validation['issues'][:5]}", "invalid_project")
    if (score_lock or not allow_score_changes) and before != result.score_fingerprint():
        raise SVError("Recipe violates --score-lock; no output written", "score_locked")
    return result
