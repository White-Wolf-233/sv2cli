"""SV2 expression and explicit pitch curves; score timing is never shortened implicitly."""
import uuid
from .errors import SVError
from .project import numeric,integer
from .timing import from_seconds


def validate_controls(controls):
    if not isinstance(controls,list):raise SVError('controls must be an array')
    seen=set()
    for c in controls:
        if not isinstance(c,dict) or c.get('type') not in {'point','curve'}:
            raise SVError('Each pitch control needs type point/curve and native pos/pitch/id fields')
        integer(c.get('pos'),'control position');numeric(c.get('pitch'),'control pitch',-128,255)
        identifier=c.get('id')
        if not isinstance(identifier,str) or not identifier.isascii() or not identifier.isdecimal() or not 0<=int(identifier)<2**64:
            raise SVError('Control id must be an unsigned 64-bit decimal string')
        if identifier in seen:raise SVError('Duplicate pitch control id')
        seen.add(identifier)
        if c['type']=='curve':
            points=c.get('points')
            if not isinstance(points,list) or len(points)<4 or len(points)%2:raise SVError('Curve points must be flat [blick,semitones,...], at least two pairs')
            times=[]
            for t,p in zip(points[::2],points[1::2]):
                times.append(integer(t,'curve point position'));numeric(p,'curve point pitch',-255,255)
            if any(b<=a for a,b in zip(times,times[1:])):raise SVError('Curve point times must strictly increase')
    return controls


def selected(group,ref,op):
    return [n for n in group.get('notes',[]) if
            (not op.get('uuids') or n.get('uuid') in op['uuids'])
            and ('start' not in op or n['onset']+ref.get('blickOffset',0)>=op['start'])
            and ('end' not in op or n['onset']+ref.get('blickOffset',0)<op['end'])]


def expression(notes,preset,vibrato=None):
    if preset not in {'rigid','default'}:raise SVError('Expression preset must be rigid or default')
    if vibrato is not None:numeric(vibrato,'vibrato modulation',0,2)
    for n in notes:
        attrs=n.setdefault('attributes',{})
        if preset=='rigid':attrs.update(expValueX=0.,expValueY=0.)
        else:
            attrs.pop('expValueX',None);attrs.pop('expValueY',None)
        if vibrato is not None:attrs['dF0VbrMod']=vibrato


def flatten(project,group,ref,notes,transition_ms=10,replace_controls=False):
    numeric(transition_ms,'transition milliseconds',0,500)
    if not isinstance(replace_controls,bool):raise SVError('replaceControls must be boolean')
    notes=sorted((n for n in notes if not n.get('attributes',{}).get('muted')),key=lambda n:n['onset'])
    if not notes:return 0
    for a,b in zip(notes,notes[1:]):
        if a['onset']+a['duration']>b['onset']:raise SVError('Flatten requires a monophonic group; split overlapping notes first','vocal_polyphony')
    existing=group.get('pitchControls',[])
    deviation=group.get('parameters',{}).get('pitchDelta',{}).get('points',[])
    if existing or deviation:
        if not replace_controls:raise SVError('Existing pitch edits would conflict. Use --replace-controls explicitly on the entire group, or retain those edits.','pitch_edit_conflict')
        if len(notes)!=len(group.get('notes',[])):raise SVError('Replacing existing pitch edits requires selecting the entire group','pitch_edit_conflict')
        existing=[]
        group.setdefault('parameters',{})['pitchDelta']={'mode':'linear','points':[]}
    islands=[]
    for n in notes:
        if islands and islands[-1][-1]['onset']+islands[-1][-1]['duration']==n['onset']:islands[-1].append(n)
        else:islands.append([n])
    offset=ref.get('blickOffset',0);curves=[]
    def pitch(n):return n['pitch']+n.get('detune',0)/100
    for island in islands:
        start=island[0]['onset'];anchor=pitch(island[0]);points={start:anchor}
        for previous,n in zip(island,island[1:]):
            boundary=n['onset'];absolute=offset+boundary
            seconds=project.seconds(absolute)
            left=max(1,absolute-from_seconds(project,seconds-transition_ms/2000))
            right=max(0,from_seconds(project,seconds+transition_ms/2000)-absolute)
            left=min(left,max(1,previous['duration']//3));right=min(right,max(0,n['duration']//3))
            points[boundary-left]=pitch(previous);points[boundary+right]=pitch(n)
        last=island[-1];points[last['onset']+last['duration']]=pitch(last)
        curves.append({'id':str(uuid.uuid4().int & ((1<<63)-1)),'type':'curve','pos':start,'pitch':anchor,
                       'points':[v for t,p in sorted(points.items()) for v in (t-start,p-anchor)]})
    group['pitchControls']=existing+curves
    return len(curves)


def articulate(project,ref,notes,gap_ms):
    numeric(gap_ms,'gap milliseconds',.01,1000)
    for n in notes:
        end=n['onset']+ref.get('blickOffset',0)+n['duration']
        new_end=from_seconds(project,project.seconds(end)-gap_ms/1000)
        duration=new_end-n['onset']-ref.get('blickOffset',0)
        if duration<1:raise SVError(f'Gap would erase note {n.get("uuid")}; choose a smaller gap','invalid_articulation')
        n['duration']=integer(duration,'articulated duration')
