"""Lossless JSON project access and conservative SV2 format validation."""
from copy import deepcopy
import hashlib
import json
import math
import re
import uuid
from .errors import SVError
from .io import read_json, write_json

QUARTER = 705600000
PARAMETERS = {"pitchDelta", "vibratoEnv", "loudness", "tension", "breathiness", "voicing", "gender", "toneShift", "mouthOpening"}
VOICE_RANGES = {"paramGender": (-1, 1), "paramToneShift": (-400, 400), "paramBreathiness": (-1, 1), "paramTension": (-1, 1), "paramLoudness": (-48, 24), "choirNumStems": (1, 16), "choirSeatingSeparation": (0, 1)}

def guid():
    return str(uuid.uuid4())

def finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise SVError(f"{label} must be a finite number")
    return value

def integer(value, label):
    finite(value, label)
    if int(value) != value:
        raise SVError(f"{label} must be an integer")
    return int(value)

def numeric(value, label, low, high):
    finite(value, label)
    if not low <= value <= high:
        raise SVError(f"{label} must be in [{low}, {high}]")
    return value

def canonical_numbers(value):
    if isinstance(value,dict):return {k:canonical_numbers(v) for k,v in value.items()}
    if isinstance(value,list):return [canonical_numbers(v) for v in value]
    if isinstance(value,float) and math.isfinite(value) and value.is_integer():return int(value)
    return value

def empty_group(name="main"):
    return {"name": name, "uuid": guid(), "notes": [], "parameters": {p: {"mode": "cubic", "points": []} for p in sorted(PARAMETERS)}, "vocalModes": {}, "pitchControls": []}

def empty_ref(group):
    return {"uuid": guid(), "groupID": group["uuid"], "blickOffset": 0, "pitchOffset": 0, "blickAbsoluteBegin": 0, "blickAbsoluteEnd": -1, "mute": False, "isInstrumental": False, "database": {"name": "", "language": "", "phoneset": "", "languageOverride": "", "phonesetOverride": "", "backendType": "", "version": "-2"}, "voice": {"vocalModeInherited": True}, "timestampLMR": 0, "timestampLRSR": 0}

def empty_track(name):
    g = empty_group()
    return {"name": name, "dispColor": "ff7db235", "dispOrder": 0, "renderEnabled": True, "mixer": {"gainDecibel": 0, "pan": 0, "mute": False, "solo": False, "fxParams": {}}, "mainGroup": g, "mainRef": empty_ref(g), "groups": []}

def new_project(name="Track 1", bpm=120):
    numeric(bpm, "bpm", 1, 999)
    return Project({"version": 196, "uuid": guid(), "time": {"meter": [{"index": 0, "numerator": 4, "denominator": 4}], "tempo": [{"position": 0, "bpm": bpm}], "startTimeSeconds": 0}, "tracks": [empty_track(name)], "library": [], "renderConfig": {"destination": "", "filename": "render", "numChannels": 2, "sampleRate": 44100, "bitDepth": 16, "aspirationFormat": "noAspiration", "exportMixDown": True, "exportPitch": False, "bypassGain": False, "bypassPan": False, "bypassEffects": False}, "projectMixer": {}})

class Project:
    def __init__(self, data):
        if not isinstance(data, dict) or not isinstance(data.get("tracks"), list) or not isinstance(data.get("library", []), list):
            raise SVError("Expected an SVP JSON object with tracks and library", "invalid_project")
        self.data = data

    @classmethod
    def load(cls, path):
        return cls(read_json(path))

    def copy(self):
        return Project(deepcopy(self.data))

    def save(self, path, force=False):
        return write_json(path, self.data, force)

    def tracks(self, selectors=None):
        tracks = self.data["tracks"]
        if not selectors:
            return list(enumerate(tracks))
        selected = set()
        for selector in selectors:
            if selector.startswith("#"):
                try:
                    i = int(selector[1:]) - 1
                except ValueError as e:
                    raise SVError("Track index must use #1, #2, ...") from e
                if i < 0 or i >= len(tracks):
                    raise SVError(f"Track index out of range: {selector}")
                selected.add(i)
            else:
                hits = [i for i, t in enumerate(tracks) if t.get("name") == selector]
                if len(hits) != 1:
                    raise SVError(f"Track name must match exactly once: {selector!r}; use #N for ambiguous names")
                selected.add(hits[0])
        return [(i, t) for i, t in enumerate(tracks) if i in selected]

    def references(self, track):
        lib = {g.get("uuid"): g for g in self.data.get("library", [])}
        if "mainGroup" in track and "mainRef" in track:
            yield track["mainRef"], track["mainGroup"]
        for ref in track.get("groups", []):
            group = lib.get(ref.get("groupID"))
            if group is None:
                raise SVError(f"Missing library group {ref.get('groupID')}", "invalid_project")
            yield ref, group

    def notes(self, selectors=None):
        rows = []
        for ti, track in self.tracks(selectors):
            for gi, (ref, group) in enumerate(self.references(track)):
                offset = ref.get("blickOffset", 0)
                for ni, note in enumerate(group.get("notes", [])):
                    rows.append({"track": ti+1, "trackName": track.get("name", ""), "group": gi, "groupID": group.get("uuid"), "note": ni, "uuid": note.get("uuid"), "onset": offset+note.get("onset", 0), "duration": note.get("duration", 0), "pitch": ref.get("pitchOffset", 0)+note.get("pitch", 0), "lyrics": note.get("lyrics", ""), "phonemes": note.get("phonemes", ""), "musicalType": note.get("musicalType", "singing"), "muted": ref.get("mute", False) or note.get("attributes", {}).get("muted", False)})
        return rows

    def score_fingerprint(self):
        # Tuning, IDs and render state are deliberately excluded; performed
        # pitches/timing, lyrics, phonemes, tempo, meter and arrangement are locked.
        rows = self.notes()
        fields = ("track", "onset", "duration", "pitch", "lyrics", "phonemes", "musicalType", "muted")
        payload = {"notes": [{k:r[k] for k in fields} for r in rows], "time": self.data.get("time"), "trackCount": len(self.data["tracks"])}
        return hashlib.sha256(json.dumps(canonical_numbers(payload), sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def seconds(self, blick):
        marks = sorted(self.data.get("time", {}).get("tempo", []), key=lambda x:x["position"])
        if not marks or marks[0]["position"] != 0:
            raise SVError("Tempo map must start at position 0")
        pos = 0
        seconds = self.data.get("time", {}).get("startTimeSeconds", 0)
        bpm = marks[0]["bpm"]
        for m in marks[1:]:
            if m["position"] >= blick:
                break
            seconds += (m["position"]-pos)/QUARTER*60/bpm
            pos, bpm = m["position"], m["bpm"]
        return seconds+(blick-pos)/QUARTER*60/bpm

    def summary(self):
        rows = self.notes()
        end = max((r["onset"]+r["duration"] for r in rows), default=0)
        ts = []
        for i, track in self.tracks():
            ns = [r for r in rows if r["track"] == i+1]
            dbs = []
            for ref, _ in self.references(track):
                db = ref.get("database", {})
                if db.get("name"):
                    dbs.append(db["name"])
            ts.append({"index": i+1, "name": track.get("name"), "notes": len(ns), "pitchRange": [min(r["pitch"] for r in ns), max(r["pitch"] for r in ns)] if ns else None, "voices": sorted(set(dbs)), "mixer": track.get("mixer", {}), "renderEnabled": track.get("renderEnabled", False)})
        return {"version": self.data.get("version"), "uuid": self.data.get("uuid"), "tracks": ts, "noteCount": len(rows), "libraryGroups": len(self.data.get("library", [])), "endBlick": end, "durationSeconds": self.seconds(end), "scoreFingerprint": self.score_fingerprint(), "renderConfig": self.data.get("renderConfig", {})}

    def validate(self):
        issues = []
        def add(code, where, message, severity="error"):
            issues.append({"code": code, "path": where, "message": message, "severity": severity})
        def check_num(v, where, low=None, high=None, whole=False):
            try:
                finite(v, where)
                if whole:
                    integer(v, where)
                if low is not None and v < low or high is not None and v > high:
                    raise SVError("out of range")
            except SVError:
                add("invalid_number", where, "Invalid, non-finite or out-of-range number")
        ids = set()
        groups = self.data.get("library", []) + [t["mainGroup"] for t in self.data["tracks"] if "mainGroup" in t]
        group_ids = {g.get("uuid") for g in groups}
        for gi, g in enumerate(groups):
            where = f"groups[{gi}]"
            if not g.get("uuid") or g["uuid"] in ids:
                add("group_uuid", where, "Missing or duplicate group UUID")
            ids.add(g.get("uuid"))
            nids = set()
            for ni, n in enumerate(g.get("notes", [])):
                p = f"{where}.notes[{ni}]"
                if not re.fullmatch(r"[0-9a-fA-F]{16}", str(n.get("uuid", ""))):
                    add("note_uuid", p+".uuid", "SV2 note UUID must be 16 hex digits")
                elif n["uuid"] in nids:
                    add("duplicate_note_uuid", p, "Duplicate note UUID in a group")
                nids.add(n.get("uuid"))
                if n.get("musicalType") == "sing":
                    add("sing_type", p+".musicalType", "Use singing, not sing")
                check_num(n.get("onset"), p+".onset", whole=True)
                check_num(n.get("duration"), p+".duration", low=1, whole=True)
                check_num(n.get("pitch"), p+".pitch", low=0, high=127, whole=True)
            for param, curve in g.get("parameters", {}).items():
                last = -float("inf")
                raw_points=curve.get("points", [])
                if raw_points and not isinstance(raw_points[0],list):
                    if len(raw_points)%2:
                        add("automation_point",where+"."+param,"Flat points must have even length")
                    points=[raw_points[i:i+2] for i in range(0,len(raw_points),2)]
                else:points=raw_points
                for pi, pair in enumerate(points):
                    if not isinstance(pair, list) or len(pair) != 2:
                        add("automation_point", where+"."+param, "Expected [blick, value]")
                        continue
                    check_num(pair[0], where+f".{param}[{pi}].position", whole=True)
                    check_num(pair[1], where+f".{param}[{pi}].value")
                    if isinstance(pair[0], (int, float)) and pair[0] <= last:
                        add("automation_order", where+"."+param, "Points must have unique increasing positions")
                    last = pair[0] if isinstance(pair[0], (int, float)) else last
        for ti, t in self.tracks():
            for ri, ref in enumerate([t.get("mainRef", {})]+t.get("groups", [])):
                if ref.get("isInstrumental"):
                    continue
                if ref.get("groupID") not in group_ids:
                    add("missing_group", f"tracks[{ti}].refs[{ri}]", "Reference points to a missing group")
                    continue
                g = next(g for g in groups if g.get("uuid") == ref.get("groupID"))
                ns = g.get("notes", [])
                if ns and all(isinstance(n.get("onset"), (int,float)) and isinstance(n.get("duration"), (int,float)) for n in ns):
                    start = ref.get("blickOffset", 0)+min(n["onset"] for n in ns)
                    end = ref.get("blickOffset", 0)+max(n["onset"]+n["duration"] for n in ns)
                    if ref.get("blickAbsoluteBegin", start) > start or (ref.get("blickAbsoluteEnd", -1) >= 0 and ref["blickAbsoluteEnd"] < end):
                        add("render_range", f"tracks[{ti}].refs[{ri}]", "Absolute render range excludes notes")
            mixer = t.get("mixer", {})
            check_num(mixer.get("pan", 0), f"tracks[{ti}].mixer.pan", -1, 1)
        marks = self.data.get("time", {}).get("tempo", [])
        if not marks or marks[0].get("position") != 0:
            add("tempo_start", "time.tempo", "Tempo map must start at position 0")
        positions = []
        for mi, m in enumerate(marks):
            check_num(m.get("position"), f"time.tempo[{mi}].position", 0, whole=True)
            check_num(m.get("bpm"), f"time.tempo[{mi}].bpm", 1, 999)
            positions.append(m.get("position"))
        if all(isinstance(p,(int,float)) for p in positions) and positions != sorted(set(positions)):
            add("tempo_order", "time.tempo", "Tempo positions must be unique and increasing")
        return {"valid": not any(i["severity"] == "error" for i in issues), "issues": issues}

    def repair(self):
        changes = []
        for g in self.data.get("library", [])+[t["mainGroup"] for t in self.data["tracks"] if "mainGroup" in t]:
            seen = set()
            for n in g.get("notes", []):
                if not re.fullmatch(r"[0-9a-fA-F]{16}", str(n.get("uuid", ""))) or n.get("uuid") in seen:
                    n["uuid"] = uuid.uuid4().hex[:16]
                    changes.append("note_uuid")
                seen.add(n["uuid"])
                if n.get("musicalType") == "sing":
                    n["musicalType"] = "singing"
                    changes.append("sing_type")
        self.update_ranges()
        return {"repairs": len(changes), "kinds": sorted(set(changes)), "validation": self.validate()}

    def update_ranges(self):
        for _, track in self.tracks():
            for ref, group in self.references(track):
                if ref.get("isInstrumental"):
                    continue
                ns = group.get("notes", [])
                off = ref.get("blickOffset", 0)
                if ns:
                    ref["blickAbsoluteBegin"] = off+min(n["onset"] for n in ns)
                    ref["blickAbsoluteEnd"] = off+max(n["onset"]+n["duration"] for n in ns)
                else:
                    ref["blickAbsoluteBegin"], ref["blickAbsoluteEnd"] = off, -1
                ref["timestampLRSR"] = 0

    def isolate_groups(self, selectors):
        """Copy-on-write: edits to shared library groups cannot leak to unselected tracks."""
        selected = {i for i,_ in self.tracks(selectors)}
        uses = {}
        for i,t in self.tracks():
            for r in t.get("groups", []):
                uses.setdefault(r["groupID"], set()).add(i)
        lib = {g["uuid"]:g for g in self.data.get("library", [])}
        clones = {}
        for i,t in self.tracks(selectors):
            for r in t.get("groups", []):
                old = r["groupID"]
                if uses.get(old, set())-selected:
                    if old not in clones:
                        g=deepcopy(lib[old]);g["uuid"]=guid()
                        self.data["library"].append(g);clones[old]=g["uuid"]
                    r["groupID"] = clones[old]

def difference(a, b):
    changes = []
    def walk(x, y, path=""):
        if type(x) is not type(y):
            changes.append({"path":path,"before":x,"after":y})
        elif isinstance(x,dict):
            for k in sorted(x.keys()|y.keys()):
                if k not in x or k not in y:
                    changes.append({"path":path+"/"+k,"before":x.get(k),"after":y.get(k)})
                else:
                    walk(x[k],y[k],path+"/"+k)
        elif isinstance(x,list):
            if len(x)!=len(y):
                changes.append({"path":path,"beforeLength":len(x),"afterLength":len(y)})
            for i,(xx,yy) in enumerate(zip(x,y)):
                walk(xx,yy,path+f"/{i}")
        elif x!=y:
            changes.append({"path":path,"before":x,"after":y})
    walk(a.data,b.data)
    return {"scoreAndTimingIdentical":a.score_fingerprint()==b.score_fingerprint(),"changeCount":len(changes),"changes":changes}
