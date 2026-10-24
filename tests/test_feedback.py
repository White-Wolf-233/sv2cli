"""Regression cases from the Winter production report and the subsequent audit."""
import json
import wave
from pathlib import Path
import pytest
from sv2cli.project import Project,QUARTER as Q,empty_ref
from sv2cli.errors import SVError
from sv2cli.edit import apply
from sv2cli.convert import midi_import,midi_export
from sv2cli.preflight import check as preflight
from sv2cli.coverage import check as coverage
from sv2cli.cli import main


def make_midi(tmp_path,events):
    import mido
    p=tmp_path/'source.mid';m=mido.MidiFile(ticks_per_beat=480);t=mido.MidiTrack();m.tracks.append(t)
    for kind,kw in events:t.append(mido.Message(kind,**kw))
    m.save(p);return p


def test_same_pitch_overlap_is_explicit_located_and_fifo(tmp_path):
    src=make_midi(tmp_path,[('note_on',dict(note=60,velocity=90,time=0)),
                            ('note_on',dict(note=60,velocity=90,time=240)),
                            ('note_off',dict(note=60,time=60)),('note_off',dict(note=60,time=180))])
    out=tmp_path/'out.svp'
    with pytest.raises(SVError,match='channel.*pitch.*truncate-overlaps'):midi_import(src,out)
    assert not out.exists()
    report={};midi_import(src,out,truncate_overlaps=True,report=report,lyric_default='a')
    assert [(n['onset'],n['duration'],n['lyrics']) for n in Project.load(out).notes()]==[(0,Q//2,'a'),(Q//2,Q//2,'a')]
    assert report['truncatedNoteCount']==1 and report['scoreChangedByPolicy']


def test_polyphony_split_keeps_all_notes_and_top_is_explicit(tmp_path):
    src=make_midi(tmp_path,[('note_on',dict(note=60,velocity=90)),('note_on',dict(note=67,velocity=90)),
                            ('note_off',dict(note=60,time=480)),('note_off',dict(note=67))])
    report={};midi_import(src,tmp_path/'preserved.svp',report=report)
    assert report['warnings'] and not preflight(Project.load(tmp_path/'preserved.svp'))['valid']
    midi_import(src,tmp_path/'split.svp',polyphony='split')
    p=Project.load(tmp_path/'split.svp')
    assert len(p.data['tracks'])==2 and preflight(p)['valid']
    assert sorted((n['onset'],n['duration'],n['pitch']) for n in p.notes())==[(0,Q,60),(0,Q,67)]
    midi_import(src,tmp_path/'top.svp',polyphony='top',report=report)
    assert [n['pitch'] for n in Project.load(tmp_path/'top.svp').notes()]==[67]
    assert report['scoreChangedByPolicy']
    with pytest.raises(SVError,match='polyphony'):midi_import(src,tmp_path/'reject.svp',polyphony='reject')


def test_midi_channels_and_simultaneous_lyrics_survive_roundtrip(project,tmp_path):
    p=apply(project,[{'op':'track.clone','tracks':['#1']}],True)
    midi_export(p,tmp_path/'out.mid');midi_import(tmp_path/'out.mid',tmp_path/'back.svp')
    assert [n['lyrics'] for n in Project.load(tmp_path/'back.svp').notes()]==[n['lyrics'] for n in p.notes()]
    src=make_midi(tmp_path,[('note_on',dict(note=60,velocity=90,channel=0)),
                            ('note_on',dict(note=60,velocity=90,channel=1)),
                            ('note_off',dict(note=60,channel=0,time=480)),('note_off',dict(note=60,channel=1))])
    midi_import(src,tmp_path/'channels.svp');assert len(Project.load(tmp_path/'channels.svp').tracks())==2
    # A chord in one track must also preserve the individual lyric/note pairing.
    p.data['tracks'][0]['mainGroup']['notes'][1]['onset']=0
    midi_export(p,tmp_path/'chord.mid');midi_import(tmp_path/'chord.mid',tmp_path/'chord.svp')
    assert [n['lyrics'] for n in Project.load(tmp_path/'chord.svp').notes()][:2]==['la','na']


def test_short_notes_never_disappear_from_activity_checks(project):
    np=pytest.importorskip('numpy')
    p=apply(project,[{'op':'notes.replace','notes':[{'onset':i*Q//8,'duration':Q//8,'pitch':60,'lyrics':'a'} for i in range(32)]}],True)
    a=np.ones((1,2000))*.1;a[:,500:1500]=0
    result=coverage(p,a,1000)
    assert result['expectedNoteCount']==32 and result['missingWindows']
    assert result['unexpectedSilence']==[{'start':.5,'end':1.5,'duration':1.}]
    assert not result['valid']


def test_coverage_ignores_rests_but_rejects_outside_audio(project):
    np=pytest.importorskip('numpy')
    p=apply(project,[{'op':'notes.shift','start':Q,'blick':4*Q}],True)
    a=np.zeros((2,3000));a[:,:500]=.1;a[:,2500:]=.1
    assert coverage(p,a,1000)['valid']
    result=coverage(p,a[:,:1000],1000)
    assert not result['valid'] and any(x['reason']=='outside_audio' for x in result['missingWindows'])


def test_rms_guard_catches_tiny_residual_noise_that_peak_gate_misses(project):
    np=pytest.importorskip('numpy');a=np.ones((2,1000))*2e-6
    result=coverage(project,a,1000)
    assert not result['missingWindows'] and result['unexpectedSilence'] and not result['valid']


def test_polyphony_across_references_is_not_hidden(project):
    from copy import deepcopy
    g=deepcopy(project.data['tracks'][0]['mainGroup']);g['uuid']='library'
    project.data['library']=[g];project.data['tracks'][0]['groups']=[empty_ref(g)];project.update_ranges()
    r=preflight(project);assert not r['valid'] and r['overlapCount']==2
    project.data['tracks'][0]['groups'][0]['mute']=True
    assert preflight(project)['valid']


def test_flat_curves_keep_score_and_constrain_transition(project):
    before=project.score_fingerprint()
    p=apply(project,[{'op':'notes.expression','preset':'rigid','vibrato':0},{'op':'pitch.flatten','transitionMs':0}],score_lock=True)
    assert p.score_fingerprint()==before
    g=p.data['tracks'][0]['mainGroup'];curve=g['pitchControls'][0]
    pairs=list(zip(curve['points'][::2],curve['points'][1::2]))
    assert (Q-1,0) in pairs and (Q,2) in pairs
    assert all(n['attributes']['expValueX']==0 for n in g['notes'])
    with pytest.raises(SVError,match='Existing pitch'):apply(p,[{'op':'pitch.flatten'}])
    p=apply(p,[{'op':'pitch.flatten','replaceControls':True}]);assert p.score_fingerprint()==before


def test_tune_cli_and_default_restore_preserve_score(project,tmp_path,capsys):
    src=tmp_path/'p.svp';out=tmp_path/'q.svp';project.save(src)
    assert main(['tune',str(src),'--mode','flat','--transition-ms','5','-o',str(out)])==0
    p=Project.load(out);assert p.score_fingerprint()==project.score_fingerprint()
    assert main(['tune',str(out),'--mode','default','--in-place'])==0
    assert 'expValueX' not in Project.load(out).data['tracks'][0]['mainGroup']['notes'][0]['attributes']


def test_explicit_articulation_is_score_locked_and_reports_invalid_gap(project):
    op={'op':'notes.articulate','gapMs':10}
    with pytest.raises(SVError,match='changes the score'):apply(project,[op])
    p=apply(project,[op],True)
    assert p.notes()[0]['duration']<project.notes()[0]['duration']
    with pytest.raises(SVError,match='erase'):apply(project,[{'op':'notes.articulate','gapMs':1000}],True)


@pytest.mark.parametrize('value',[{'reverb':{'type':'mystery'}},{'reverb':{'decay':-1}},
                                   {'reverb':{'dryWetRatio':2}},{'room':{'enable':True}},
                                   {'compressor':{'attack':True}}])
def test_effect_typos_and_invalid_ranges_fail_before_save(project,value):
    with pytest.raises(SVError):apply(project,[{'op':'effects.set','values':value}])


def test_normalize_changes_gain_only_and_dbfs_report(tmp_path):
    np=pytest.importorskip('numpy')
    from sv2cli.pcm import encode
    from sv2cli.timing import read_pcm
    from sv2cli.normalize import write
    from sv2cli.audio import check
    src=tmp_path/'source.wav';out=tmp_path/'normalized.wav'
    a=np.zeros((2,8000));a[:,1000:6000]=.1*np.sin(np.arange(5000)*.3)
    with wave.open(str(src),'wb') as w:w.setparams((2,3,8000,0,'NONE','none'));w.writeframes(encode(a,24))
    original=src.read_bytes();r=write(src,out,-1)
    b,rate,bits=read_pcm(out);assert rate==8000 and bits==24 and b.shape==a.shape and src.read_bytes()==original
    assert np.max(np.abs(b[:,0:1000]))==0 and check(out)['peakDBFS']==pytest.approx(-1,abs=.001)
    assert not r['audioTranslated'] and not r['resampled']
    with pytest.raises(SVError,match='new output'):write(src,src,-1,True)


def test_tuning_readback_rejects_silently_ignored_pitch(project):
    from sv2cli.native_transport import verify_tuning
    p=apply(project,[{'op':'notes.expression','preset':'rigid'},{'op':'pitch.flatten'}])
    with pytest.raises(SVError,match='pitch controls'):verify_tuning(p,project)
    verify_tuning(p,p.copy())


def test_version_metadata_is_consistent():
    import re,sv2cli
    text=(Path(__file__).parents[1]/'pyproject.toml').read_text('utf8')
    assert re.search(r'^version = "([^"]+)"',text,re.M).group(1)==sv2cli.__version__


def test_polyphonic_render_rejected_without_starting_worker(project,tmp_path,monkeypatch):
    from sv2cli.render import render
    project.data['tracks'][0]['mainGroup']['notes'][1]['onset']=0
    src=tmp_path/'p.svp';project.save(src)
    monkeypatch.setattr('sv2cli.render.profile',lambda name:{'render_command':['fake','{job}']})
    def forbidden(*args):pytest.fail('Polyphony must fail before spawning a backend')
    monkeypatch.setattr('sv2cli.render._worker',forbidden)
    out=tmp_path/'out.wav'
    with pytest.raises(SVError) as error:render(src,out,backend='command')
    assert error.value.code=='vocal_polyphony' and not out.exists()


def test_every_stem_uses_full_project_timeline(project,tmp_path,monkeypatch):
    from sv2cli.render import render
    p=apply(project,[{'op':'track.clone','tracks':['#1']},
                     {'op':'notes.shift','tracks':['#2'],'blick':4*Q}],True)
    src=tmp_path/'p.svp';p.save(src);durations=[]
    def backend(command,timeout,log):
        j=json.loads(Path(command[-1]).read_text('utf8'));durations.append(j['duration'])
        with wave.open(str(log.parent/'render.wav'),'wb') as w:
            w.setparams((2,2,22050,0,'NONE','none'));w.writeframes(b'\xe8\x03'*2*round(j['duration']*22050))
    monkeypatch.setattr('sv2cli.render.profile',lambda name:{'render_command':['fake','{job}']})
    monkeypatch.setattr('sv2cli.render._worker',backend)
    render(src,tmp_path/'stems',backend='command',stems=True,sample_rate=22050)
    assert durations==[5.,5.]


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1])
def test_audio_check_rejects_invalid_expected_duration(tmp_path,value):
    from sv2cli.audio import check
    with pytest.raises(SVError):check(tmp_path/'anything.wav',expected_seconds=value)


def test_invalid_pitch_curves_fail_before_project_write(project):
    with pytest.raises(SVError,match='strictly increase'):
        apply(project,[{'op':'pitch.controls','controls':[{'id':'1','type':'curve','pos':0,'pitch':60,'points':[0,0,0,1]}]}])


def test_meter_and_expression_invalid_values_are_reported(project):
    project.data['time']['meter']=[{'index':0,'numerator':0,'denominator':3}]
    project.data['tracks'][0]['mainGroup']['notes'][0]['attributes']['expValueX']=2
    report=project.validate()
    assert not report['valid'] and {'meter_map','invalid_number'}<={x['code'] for x in report['issues']}


def test_tuning_readback_rejects_clamped_effects(project):
    from sv2cli.native_transport import verify_tuning
    p=apply(project,[{'op':'effects.set','values':{'reverb':{'preDelay':.025}}}])
    with pytest.raises(SVError) as e:verify_tuning(p,project)
    assert e.value.code=='effect_load_mismatch'


def test_midi_ambiguous_export_fails_but_csv_is_lossless(project,tmp_path):
    from sv2cli.convert import csv_export
    notes=project.data['tracks'][0]['mainGroup']['notes']
    notes[1].update(onset=Q//2,pitch=notes[0]['pitch'])
    with pytest.raises(SVError,match='ambiguous'):midi_export(project,tmp_path/'bad.mid')
    assert not (tmp_path/'bad.mid').exists()
    csv_export(project,tmp_path/'notes.csv')
    assert (tmp_path/'notes.csv').exists()


def test_disabled_solo_does_not_hide_enabled_voice(project):
    p=apply(project,[{'op':'track.clone','tracks':['#1']}],True)
    p.data['tracks'][1]['renderEnabled']=False;p.data['tracks'][1]['mixer']['solo']=True
    assert preflight(p)['valid'] and preflight(p)['audibleNotes']==2
