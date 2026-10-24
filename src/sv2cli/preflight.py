"""Score-aware vocal preflight. Polyphony is valid notation, not a valid solo voice."""
from .errors import SVError


def audible_notes(project, selectors=None):
    mixes={i+1:t.get('mixer',{}) for i,t in project.tracks()}
    enabled={i+1 for i,t in project.tracks() if t.get('renderEnabled',True)}
    solos={i for i,m in mixes.items() if m.get('solo') and not m.get('mute') and i in enabled}
    return [n for n in project.notes(selectors) if not n['muted']
            and n['track'] in enabled and not mixes[n['track']].get('mute')
            and (not solos or n['track'] in solos)]


def overlaps(rows):
    """Find overlapping intervals per vocal track, including different references."""
    result=[];active={}
    for n in sorted(rows,key=lambda n:(n['onset'],n['track'],n['pitch'])):
        track=n['track'];live=[p for p in active.get(track,[]) if p['onset']+p['duration']>n['onset']]
        for p in live:
            result.append({'track':track,'trackName':n.get('trackName',''),
                           'onset':n['onset'],'end':min(n['onset']+n['duration'],p['onset']+p['duration']),
                           'pitches':[p['pitch'],n['pitch']],
                           'noteIDs':[p.get('uuid'),n.get('uuid')],
                           'referenceIDs':[p.get('referenceID'),n.get('referenceID')]})
        live.append(n);active[track]=live
    return result


def check(project, selectors=None):
    validation=project.validate()
    if not validation['valid']:
        return {'valid':False,'issues':validation['issues'],'scoreUnchanged':True}
    rows=audible_notes(project,selectors);poly=overlaps(rows)
    for item in poly:
        item['seconds']=project.seconds(item['onset'])
    short=[n for n in rows if project.seconds(n['onset']+n['duration'])-project.seconds(n['onset'])<=.25]
    issues=[]
    if poly:issues.append({'code':'vocal_polyphony','severity':'error','count':len(poly),
                          'message':'A vocal track must be monophonic. Split voices explicitly; MIDI import supports --polyphony split or --top-voice.',
                          'examples':poly[:20]})
    if not rows:issues.append({'code':'no_audible_notes','severity':'error','message':'No audible, render-enabled notes selected.'})
    if short:issues.append({'code':'short_notes','severity':'warning','count':len(short),
                           'message':'Short notes are checked for activity, but energy cannot certify each rapid note or consonant.'})
    if rows and all(n['lyrics']=='la' for n in rows):
        issues.append({'code':'default_lyrics','severity':'warning','message':'Every selected note uses la. MIDI import accepts --lyric-default.'})
    return {'valid':not any(x['severity']=='error' for x in issues),'issues':issues,
            'audibleNotes':len(rows),'shortNotes':len(short),'overlapCount':len(poly),
            'scoreFingerprint':project.score_fingerprint(),'scoreUnchanged':True,
            'allNoteOnsetsVerified':False,'phonemeAlignmentVerified':False}


def require_monophonic(project):
    report=check(project)
    if not report['valid']:
        issue=next(x for x in report['issues'] if x['severity']=='error')
        raise SVError(f"Vocal preflight failed: {issue}. Run preflight PROJECT for locations; no synthesis was started.",issue['code'])
    return report
