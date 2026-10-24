"""Exact MIDI import with explicit, reported transformations."""
from collections import defaultdict, deque
from copy import deepcopy
from fractions import Fraction
from .errors import SVError
from .project import new_project,empty_track,QUARTER
from .preflight import overlaps


def _voices(rows,policy):
    if policy=='split':
        voices=[];ends=[]
        for n in sorted(rows,key=lambda n:(n['onset'],n['pitch'])):
            available=[i for i,end in enumerate(ends) if end<=n['onset']]
            i=max(available,key=lambda i:ends[i]) if available else len(voices)
            if i==len(voices):voices.append([]);ends.append(0)
            voices[i].append(n);ends[i]=n['onset']+n['duration']
        return voices
    if policy=='top':
        events=defaultdict(list)
        for i,n in enumerate(rows):
            events[n['onset']].append((1,i));events[n['onset']+n['duration']].append((-1,i))
        active=set();selected=[];positions=sorted(events)
        for a,b in zip(positions,positions[1:]):
            for state,i in events[a]:
                if state==1:active.add(i)
                else:active.discard(i)
            if not active:continue
            i=max(active,key=lambda i:(rows[i]['pitch'],-rows[i]['onset'],-i))
            if selected and selected[-1][0]==i and selected[-1][1]['onset']+selected[-1][1]['duration']==a:
                selected[-1][1]['duration']+=b-a
            else:selected.append((i,{**rows[i],'onset':a,'duration':b-a}))
        return [[n for _,n in selected]]
    return [rows]


def load(source,*,truncate_overlaps=False,polyphony='preserve',lyric_default='la',charset='utf8'):
    from .convert import _mido
    import codecs
    try:codecs.lookup(charset)
    except LookupError as e:raise SVError(f'Unknown MIDI text encoding: {charset}') from e
    if polyphony not in {'preserve','reject','split','top'}:raise SVError('Use preserve/reject/split/top for polyphony')
    if not isinstance(lyric_default,str):raise SVError('Default lyric must be text')
    mido=_mido();midi=mido.MidiFile(source,charset=charset)
    if midi.type==2:raise SVError('Asynchronous type-2 MIDI is unsupported','unsupported_format')
    if midi.ticks_per_beat<=0:raise SVError('SMPTE MIDI timecode is unsupported','unsupported_format')
    report={'source':str(source),'polyphonyPolicy':polyphony,'lyricDefault':lyric_default,
            'truncateOverlaps':truncate_overlaps,'samePitchPairing':'FIFO note-offs',
            'truncatedNotes':[],'discardedZeroLengthNotes':[],'warnings':[],'inputNotes':0,'outputNotes':0,'tracks':[]}
    project=new_project();project.data['tracks']=[];tempos={0:120};meters={}
    def blick(tick):
        x=Fraction(tick*QUARTER,midi.ticks_per_beat)
        if x.denominator!=1:raise SVError(f'MIDI tick {tick} cannot be represented exactly as blicks','lossy_conversion')
        return int(x)
    for ti,track in enumerate(midi.tracks,1):
        when=0;pending=defaultdict(deque);notes=[];name=f'Track {ti}';lyric=lyric_default
        for ei,msg in enumerate(track,1):
            when+=msg.time
            if msg.type=='track_name':name=msg.name
            elif msg.type=='set_tempo':
                value=mido.tempo2bpm(msg.tempo)
                if when in tempos and when!=0 and tempos[when]!=value:raise SVError(f'Conflicting tempos at MIDI tick {when}','invalid_file')
                tempos[when]=value
            elif msg.type=='time_signature':
                value=(msg.numerator,msg.denominator)
                if when in meters and meters[when]!=value:raise SVError(f'Conflicting meters at MIDI tick {when}','invalid_file')
                meters[when]=value
            elif msg.type=='lyrics':lyric=msg.text
            elif msg.type=='note_on' and msg.velocity:
                key=(msg.channel,msg.note)
                for old in pending[key]:
                    if old['end'] is not None:continue
                    detail={'midiTrack':ti,'trackName':name,'channel':msg.channel+1,'pitch':msg.note,
                            'startTick':old['start'],'nextOnsetTick':when,'event':ei}
                    if not truncate_overlaps:
                        raise SVError(f'Overlapping same-pitch MIDI notes: {detail}. Use --truncate-overlaps explicitly, or repair the source.','lossy_conversion')
                    old['end']=when;report['truncatedNotes'].append(detail)
                n={'start':when,'end':None,'pitch':msg.note,'lyrics':lyric,'channel':msg.channel}
                notes.append(n);pending[key].append(n);lyric=lyric_default;report['inputNotes']+=1
            elif msg.type in {'note_on','note_off'}:
                q=pending[(msg.channel,msg.note)]
                if q:
                    n=q.popleft()
                    if n['end'] is None:n['end']=when
            elif msg.type=='control_change' and msg.control in {64,66,67}:
                if 'Pedal controllers are not converted to vocal note durations.' not in report['warnings']:
                    report['warnings'].append('Pedal controllers are not converted to vocal note durations.')
        unfinished=[n for n in notes if n['end'] is None]
        if unfinished:raise SVError(f'MIDI track {ti} ({name}) contains unclosed notes: {unfinished[:3]}','invalid_file')
        for n in notes:
            if n['end']==n['start']:
                report['discardedZeroLengthNotes'].append({'midiTrack':ti,'channel':n['channel']+1,'pitch':n['pitch'],'tick':n['start']})
        channels=sorted({n['channel'] for n in notes})
        for channel in channels:
            rows=[{'onset':blick(n['start']),'duration':blick(n['end']-n['start']),
                   'pitch':n['pitch'],'lyrics':n['lyrics']} for n in notes if n['channel']==channel and n['end']>n['start']]
            if not rows:continue
            rows.sort(key=lambda n:(n['onset'],n['pitch']))
            poly=overlaps([{**n,'track':1} for n in rows])
            if poly and polyphony=='reject':
                raise SVError(f'MIDI track {ti} ({name}), channel {channel+1} has polyphony: {poly[:3]}. Use --polyphony split, or explicit --top-voice.','vocal_polyphony')
            if poly and polyphony=='preserve':report['warnings'].append(f'Track {ti} ({name}), channel {channel+1}: {len(poly)} overlapping pairs preserved. Vocal rendering will require splitting.')
            voices=_voices(rows,polyphony)
            for vi,voice in enumerate(voices,1):
                title=name+(f' [ch {channel+1}]' if len(channels)>1 else '')+(f' [voice {vi}]' if len(voices)>1 else '')
                t=empty_track(title)
                from .edit import _new_note
                t['mainGroup']['notes']=[_new_note(n) for n in voice]
                project.data['tracks'].append(t);report['outputNotes']+=len(voice)
                report['tracks'].append({'name':title,'midiTrack':ti,'channel':channel+1,'notes':len(voice)})
    if not project.data['tracks']:raise SVError('MIDI contains no positive-duration notes','invalid_file')
    project.data['time']['tempo']=[{'position':blick(t),'bpm':v} for t,v in sorted(tempos.items())]
    last=bar=0;num=den=4;marks=[]
    for tick,(n,d) in sorted(meters.items()):
        bars=Fraction((tick-last)*den,midi.ticks_per_beat*num*4)
        if bars.denominator!=1:raise SVError(f'Meter change at MIDI tick {tick} is not at a bar boundary','lossy_conversion')
        bar+=int(bars);marks.append({'index':bar,'numerator':n,'denominator':d});last=tick;num=n;den=d
    if marks:project.data['time']['meter']=marks if marks[0]['index']==0 else [{'index':0,'numerator':4,'denominator':4}]+marks
    project.update_ranges()
    if not project.validate()['valid']:raise SVError('Imported MIDI project is invalid','invalid_project')
    report.update(truncatedNoteCount=len(report['truncatedNotes']),scoreChangedByPolicy=bool(report['truncatedNotes'] or report['discardedZeroLengthNotes']) or polyphony=='top',
                  polyphonySplit=polyphony=='split',exactBlickTiming=True)
    return project,report
