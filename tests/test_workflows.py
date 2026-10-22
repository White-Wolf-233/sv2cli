from copy import deepcopy
import json
from pathlib import Path
import wave
import sys
import pytest
from sv2cli.project import Project, QUARTER as Q, empty_ref, empty_track
from sv2cli.edit import apply
from sv2cli.errors import SVError
from sv2cli.cli import main, _parser, execute
from sv2cli.io import write_json
from sv2cli.timing import position, describe, check, shift

def linked(project, across=False):
    p=project.copy();t=p.data['tracks'][0];g=deepcopy(t['mainGroup'])
    g['uuid']='shared';t['mainGroup']['notes']=[];t['groups']=[empty_ref(g)]
    r=empty_ref(g);r['blickOffset']=4*Q
    if across:
        t2=empty_track('Backing');t2['groups']=[r];p.data['tracks'].append(t2)
    else:t['groups'].append(r)
    p.data['library'].append(g);p.update_ranges();return p

@pytest.mark.parametrize('across',[False,True])
@pytest.mark.parametrize('start',[0,4*Q])
def test_reference_time_selection_does_not_leak(project,across,start):
    p=linked(project,across)
    q=apply(p,[{'op':'notes.transpose','start':start,'end':start+2*Q,'semitones':12}],True)
    assert [n['pitch'] for n in q.notes()]==([72,74,60,62] if start==0 else [60,62,72,74])
    assert [n['pitch'] for n in p.notes()]==[60,62,60,62]

def test_uuid_resolves_before_copy_and_reference_id_can_select_one(project):
    p=linked(project,True)
    q=apply(p,[{'op':'notes.transpose','tracks':['#1'],'groups':['shared'],'semitones':12}],True)
    assert [n['pitch'] for n in q.notes()]==[72,74,60,62]
    p=linked(project)
    ref=p.data['tracks'][0]['groups'][1]['uuid']
    q=apply(p,[{'op':'notes.transpose','references':[ref],'semitones':12}],True)
    assert [n['pitch'] for n in q.notes()]==[60,62,72,74]
    q=apply(p,[{'op':'notes.transpose','groups':['shared'],'references':[ref],'semitones':12},
               {'op':'notes.transpose','groups':['shared'],'references':[ref],'semitones':-12}],True)
    assert q.score_fingerprint()==p.score_fingerprint()

def test_unknown_fields_empty_selection_and_effective_pitch_rejected(project):
    for ops,allow in [([{'op':'mixer.set','track':['#1'],'values':{'gainDecibel':-6}}],False),
                      ([{'op':'notes.transpose','semitones':12,'uuids':['missing']}],True),
                      ([{'op':'group.transpose','semitones':100}],True)]:
        with pytest.raises(SVError):apply(project,ops,allow)

def test_midi_selection_and_batch_profile_and_errors(project,tmp_path,monkeypatch):
    p=apply(project,[{'op':'track.clone','tracks':['#1']}],True)
    p=apply(p,[{'op':'notes.transpose','tracks':['#2'],'semitones':12}],True)
    src=tmp_path/'p.svp';p.save(src);mid=tmp_path/'one.mid'
    execute(_parser().parse_args(['convert','midi-out',str(src),'--track','#2','-o',str(mid)]))
    import mido
    assert [m.note for t in mido.MidiFile(mid).tracks for m in t if m.type=='note_on']==[72,74]
    cfg=tmp_path/'cfg.json';write_json(cfg,{'profiles':{'studio':{},'other':{}}});monkeypatch.setenv('SV2CLI_CONFIG',str(cfg))
    recipe=tmp_path/'bad.json';write_json(recipe,[{'op':'notes.transpose'}])
    batch=tmp_path/'batch.json'
    write_json(batch,[['edit',str(src),'--recipe',str(recipe),'--allow-score-changes','-o',str(tmp_path/'out.svp')],['doctor'],['--profile','other','doctor']])
    result=execute(_parser().parse_args(['--profile','studio','batch',str(batch),'--keep-going']))
    assert [r['ok'] for r in result['jobs']]==[False,True,True]
    assert result['jobs'][1]['result']['profile']=='studio'
    assert result['jobs'][2]['result']['profile']=='other'

def test_in_place_is_atomic_backed_up_and_dry_run_has_no_side_effect(project,tmp_path,capsys):
    p=tmp_path/'song.svp';project.save(p);old=p.read_bytes()
    assert main(['mixer',str(p),'--in-place','--gain','-4','--dry-run'])==0
    assert p.read_bytes()==old and not list(tmp_path.glob('*.bak'))
    assert main(['mixer',str(p),'--in-place','--gain','-4'])==0
    assert next(tmp_path.glob('*.bak')).read_bytes()==old
    assert Project.load(p).data['tracks'][0]['mixer']['gainDecibel']==-4
    assert Project.load(p).score_fingerprint()==project.score_fingerprint()
    bad=tmp_path/'bad.json';write_json(bad,[{'op':'group.transpose','semitones':100}]);before=p.read_bytes()
    assert main(['edit',str(p),'--recipe',str(bad),'--allow-score-changes','--in-place'])==2
    assert p.read_bytes()==before

def test_musical_coordinates_with_meter_tempo_and_offset(project):
    project.data['time']={'startTimeSeconds':2,'tempo':[{'position':0,'bpm':120},{'position':4*Q,'bpm':60}],
                          'meter':[{'index':0,'numerator':4,'denominator':4},{'index':1,'numerator':6,'denominator':8}]}
    assert position(project,'bar:2:4')==int(5.5*Q)
    assert position(project,'q:11/2')==int(5.5*Q)
    assert position(project,'s:5.5')==int(5.5*Q)
    assert describe(project,'bar:2:4')['beat']==4
    assert describe(project,'bar:2:4')['seconds']==5.5
    with pytest.raises(SVError):position(project,'bar:2:7')

def test_failed_atomic_replace_keeps_source_and_backup(project,tmp_path,monkeypatch,capsys):
    import sv2cli.io as io_module
    src=tmp_path/'song.svp';project.save(src);before=src.read_bytes()
    def denied(*args):raise PermissionError('controlled locked file')
    monkeypatch.setattr(io_module.os,'replace',denied)
    assert main(['mixer',str(src),'--gain','-3','--in-place'])==2
    assert src.read_bytes()==before and next(tmp_path.glob('*.bak')).read_bytes()==before
    assert not list(tmp_path.glob('.sv2cli-*'))

def test_invalid_reference_offset_is_reported(project):
    project.data['tracks'][0]['mainRef']['blickOffset']='bad'
    assert not project.validate()['valid']

def test_audio_entries_legato_and_shift_regression(project,tmp_path):
    np=pytest.importorskip('numpy');rate=1000
    project=apply(project,[{'op':'notes.shift','blick':Q}],True)
    audio=np.zeros((1,2500));audio[:,700:1000]=.1;audio[:,1200:1500]=.1
    report=check(project,audio,rate,['#1'])
    assert len(report['notes'])==2
    assert report['notes'][0]['entryDeltaSeconds']==pytest.approx(.2,abs=.01)
    assert report['notes'][1]['observedEntrySeconds'] is None
    assert report['alignmentVerified'] is False
    selected=check(project,audio,rate,['#1'],start='q:2',end='q:3')
    assert len(selected['notes'])==1 and selected['notes'][0]['observedEntrySeconds'] is None
    src=tmp_path/'late.wav'
    from sv2cli.pcm import encode
    with wave.open(str(src),'wb') as f:
        f.setparams((1,2,rate,0,'NONE','none'));f.writeframes(encode(audio,16))
    result=shift(project,src,tmp_path/'aligned.wav',['#1'],-.2)
    assert result['after']['notes'][0]['entryDeltaSeconds']==pytest.approx(0,abs=.01)
    with pytest.raises(SVError,match='discard'):shift(project,src,tmp_path/'crop.wav',['#1'],-.8)
    with pytest.raises(SVError,match='previously active'):shift(project,src,tmp_path/'lost.wav',['#1'],1.)
    assert not (tmp_path/'crop.wav').exists() and not (tmp_path/'lost.wav').exists()

def test_resume_only_verified_outputs_and_reject_changed_voice(project,tmp_path,monkeypatch):
    from sv2cli.render import render
    p=apply(project,[{'op':'track.clone','tracks':['#1']}],True)
    src=tmp_path/'p.svp';p.save(src);dest=tmp_path/'stems';calls=[]
    def worker(command,timeout,log):
        calls.append(log.parent.name)
        if len(calls)==2:raise SVError('controlled failure')
        j=json.loads(Path(command[-1]).read_text())
        with wave.open(str(log.parent/'render.wav'),'wb') as f:
            f.setparams((2,2,22050,0,'NONE','none'));f.writeframes(b'\xe8\x03'*2*round(j['duration']*22050))
    monkeypatch.setattr('sv2cli.render.profile',lambda name:{'render_command':['fake','{job}']})
    monkeypatch.setattr('sv2cli.render._worker',worker)
    with pytest.raises(SVError):render(src,dest,backend='command',stems=True,sample_rate=22050)
    state=json.loads((dest/'manifest.json').read_text());assert state['status']=='failed'
    status=execute(_parser().parse_args(['job-status',str(dest)]))
    assert status['completed']==1 and status['total']==2 and status['failed'][0]['trackName']
    first=(dest/'01.wav').stat().st_mtime_ns
    result=render(src,dest,backend='command',stems=True,sample_rate=22050,resume=True)
    assert result['status']=='complete' and result['audio'][0]['reused']
    assert calls==['task-1','task-2','task-2'] and (dest/'01.wav').stat().st_mtime_ns==first
    intact=(dest/'01.wav').read_bytes();(dest/'01.wav').write_bytes(b'externally changed')
    with pytest.raises(SVError,match='cannot be verified'):
        render(src,dest,backend='command',stems=True,sample_rate=22050,resume=True)
    assert len(json.loads((dest/'manifest.json').read_text())['checkpointAudio'])==2
    (dest/'01.wav').write_bytes(intact)
    result=render(src,dest,backend='command',stems=True,sample_rate=22050,resume=True)
    assert all(r['reused'] for r in result['audio']) and len(calls)==3
    changed=apply(p,[{'op':'voice.set','values':{'paramGender':.2}}]);changed.save(src,True)
    with pytest.raises(SVError,match='changed'):render(src,dest,backend='command',stems=True,sample_rate=22050,resume=True)
