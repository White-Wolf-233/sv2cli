import csv
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
    mido=_mido();midi=mido.MidiFile(ticks_per_beat=ppq,charset="utf8")
    def tick(blick):
        x=blick/QUARTER*ppq
        if abs(x-round(x))>1e-6:raise SVError("MIDI export would round a note; choose a compatible --ppq", "lossy_conversion")
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
    for i,t in project.tracks(selectors):
        mt=mido.MidiTrack();midi.tracks.append(mt);mt.append(mido.MetaMessage("track_name",name=t.get("name",f"Track {i+1}")))
        events=[]
        for r in rows:
            if r["track"]!=i+1:continue
            if r["musicalType"] not in {"singing","sing"}:raise SVError("MIDI export cannot preserve rap/spoken note modes", "lossy_conversion")
            on=tick(r["onset"]);off=tick(r["onset"]+r["duration"])
            events.extend([(on,1,mido.MetaMessage("lyrics",text=r["lyrics"])),(on,2,mido.Message("note_on",note=r["pitch"],velocity=80)),(off,0,mido.Message("note_off",note=r["pitch"],velocity=0))])
        prev=0
        for when,_,msg in sorted(events,key=lambda x:(x[0],x[1])):msg.time=when-prev;mt.append(msg);prev=when
    b=io.BytesIO();midi.save(file=b)
    return write_new(output,b.getvalue(),force)

def midi_import(source, output, force=False):
    mido=_mido();midi=mido.MidiFile(source,charset="utf8")
    if midi.type==2:raise SVError("Asynchronous type-2 MIDI is unsupported", "unsupported_format")
    if midi.ticks_per_beat<=0:raise SVError("SMPTE MIDI timecode is unsupported", "unsupported_format")
    project=new_project();project.data["tracks"]=[];tempos={0:120};meter_ticks=[]
    for track in midi.tracks:
        when=0;pending={};rows=[];name=f"Track {len(project.data['tracks'])+1}";lyric="la"
        for msg in track:
            when+=msg.time
            if msg.type=="track_name":name=msg.name
            elif msg.type=="set_tempo":tempos[when]=mido.tempo2bpm(msg.tempo)
            elif msg.type=="time_signature":meter_ticks.append((when,msg.numerator,msg.denominator))
            elif msg.type=="lyrics":lyric=msg.text
            elif msg.type=="note_on" and msg.velocity:
                key=(msg.channel,msg.note)
                if key in pending:raise SVError("Overlapping same-pitch MIDI notes are ambiguous", "lossy_conversion")
                pending[key]=(when,lyric);lyric="la"
            elif msg.type in {"note_off","note_on"}:
                key=(msg.channel,msg.note)
                if key not in pending:continue
                start,text=pending.pop(key)
                onset=start*QUARTER/midi.ticks_per_beat;duration=(when-start)*QUARTER/midi.ticks_per_beat
                if int(onset)!=onset or int(duration)!=duration:raise SVError("MIDI timing cannot be represented exactly as blicks", "lossy_conversion")
                if duration>0:rows.append({"onset":int(onset),"duration":int(duration),"pitch":msg.note,"lyrics":text})
        if pending:raise SVError("MIDI contains unclosed notes", "invalid_file")
        if rows:
            t=empty_track(name);project.data["tracks"].append(t)
            project=apply(project,[{"op":"notes.replace","tracks":[f"#{len(project.data['tracks'])}"],"notes":sorted(rows,key=lambda x:(x['onset'],x['pitch']))}],True)
    project.data["time"]["tempo"]=[{"position":integer(t*QUARTER/midi.ticks_per_beat,"tempo position"),"bpm":v} for t,v in sorted(tempos.items())]
    # Reject off-bar meter changes rather than silently moving them.
    meters=[];last=0;bar=0;num=4;den=4
    for tick,n,d in sorted(set(meter_ticks)):
        beats=(tick-last)/midi.ticks_per_beat;bars=beats/(num*4/den)
        if abs(bars-round(bars))>1e-6:raise SVError("Meter change is not at a bar boundary", "lossy_conversion")
        bar+=round(bars);meters.append({"index":bar,"numerator":n,"denominator":d});last=tick;num=n;den=d
    if meters:project.data["time"]["meter"]=meters if meters[0]["index"]==0 else [{"index":0,"numerator":4,"denominator":4}]+meters
    project.update_ranges()
    if not project.validate()["valid"]:raise SVError("Imported MIDI project is invalid")
    return project.save(output,force)
