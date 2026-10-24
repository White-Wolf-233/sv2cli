import csv
from fractions import Fraction
import io
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from .errors import SVError
from .io import write_new
from .project import Project, QUARTER, new_project, empty_track, integer
from .edit import apply

def csv_export(project, output, selectors=None, force=False):
    rows=project.notes(selectors)
    stream=io.StringIO(newline="")
    fields=["track","trackName","groupID","uuid","onset","duration","pitch","lyrics","phonemes","musicalType"]
    writer=csv.DictWriter(stream,fields,extrasaction="ignore");writer.writeheader();writer.writerows(rows)
    return write_new(output,"\ufeff"+stream.getvalue(),force)

def csv_import(source, project, track, output, force=False):
    with Path(source).open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    for row in rows:
        for k in ("onset","duration","pitch"):row[k]=int(row[k])
    result=apply(project,[{"op":"notes.replace","tracks":[track],"notes":rows}],True)
    return result.save(output,force)

def _mido():
    try:
        import mido
        return mido
    except ImportError as e:raise SVError("Install MIDI support: pip install 'sv2cli[midi]'", "missing_dependency") from e

def midi_export(project, output, selectors=None, force=False, ppq=960):
    ppq=integer(ppq,"MIDI PPQ")
    if not 1<=ppq<=32767:raise SVError("MIDI PPQ must be in [1,32767]")
    mido=_mido();midi=mido.MidiFile(ticks_per_beat=ppq,charset="utf8")
    def tick(blick):
        x=Fraction(blick)*ppq/QUARTER
        if x.denominator!=1:raise SVError("MIDI export would round a note; choose a compatible --ppq", "lossy_conversion")
        if x<0:raise SVError("MIDI cannot represent negative onsets", "lossy_conversion")
        return round(x)
    meta=mido.MidiTrack();midi.tracks.append(meta)
    events=[]
    for m in project.data["time"]["tempo"]:
        events.append((tick(m["position"]),mido.MetaMessage("set_tempo",tempo=mido.bpm2tempo(m["bpm"]))))
    # Meter indices are bar numbers, not quarter positions.
    meter=sorted(project.data["time"].get("meter",[]),key=lambda x:x["index"])
    bar=0;pos=0;num=4;den=4
    for mark in meter:
        pos+=(mark["index"]-bar)*num*QUARTER*4/den
        bar=mark["index"];num=mark["numerator"];den=mark["denominator"]
        events.append((tick(pos),mido.MetaMessage("time_signature",numerator=num,denominator=den)))
    prev=0
    for time,msg in sorted(events,key=lambda x:x[0]):msg.time=time-prev;meta.append(msg);prev=time
    rows=project.notes(selectors)
    from .preflight import overlaps
    ambiguous=[x for x in overlaps(rows) if x['pitches'][0]==x['pitches'][1]]
    if ambiguous:raise SVError(f'MIDI export cannot preserve ambiguous overlapping same-pitch notes: {ambiguous[:3]}','lossy_conversion')
    for i,t in project.tracks(selectors):
        mt=mido.MidiTrack();midi.tracks.append(mt);mt.append(mido.MetaMessage("track_name",name=t.get("name",f"Track {i+1}")))
        events=[]
        for r in rows:
            if r["track"]!=i+1:continue
            if r["musicalType"] not in {"singing","sing"}:raise SVError("MIDI export cannot preserve rap/spoken note modes", "lossy_conversion")
            on=tick(r["onset"]);off=tick(r["onset"]+r["duration"])
            events.extend([(on,1,mido.MetaMessage("lyrics",text=r["lyrics"])),(on,1,mido.Message("note_on",note=r["pitch"],velocity=80)),(off,0,mido.Message("note_off",note=r["pitch"],velocity=0))])
        prev=0
        for when,_,msg in sorted(events,key=lambda x:(x[0],x[1])):msg.time=when-prev;mt.append(msg);prev=when
    b=io.BytesIO();midi.save(file=b)
    return write_new(output,b.getvalue(),force)

def midi_import(source, output, force=False, *, truncate_overlaps=False, polyphony="preserve", lyric_default="la", charset="utf8", report=None):
    from .midi_importing import load
    project, details=load(source,truncate_overlaps=truncate_overlaps,polyphony=polyphony,lyric_default=lyric_default,charset=charset)
    if report is not None:report.update(details)
    return project.save(output,force)
