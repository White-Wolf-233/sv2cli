from copy import deepcopy
import json
import pytest
from sv2cli.cli import main, execute, _parser
from sv2cli.edit import apply
from sv2cli.errors import SVError
from sv2cli.lyrics import audit
from sv2cli.project import QUARTER as Q, empty_group, empty_ref, empty_track, new_project


def song(words=('山', '-', '河')):
    return apply(new_project('Lead'), [{'op':'notes.replace','notes':[
        {'onset':i*Q,'duration':Q,'pitch':60+i,'lyrics':word} for i,word in enumerate(words)]}], True)


def plan(words=('山', '-', '河')):
    return {'source':{'reference':'independent fixture','reviewed':True},'tracks':[
        {'selector':'#1','phrases':[{'id':'verse-1','start':'0','end':str(len(words)),
          'text':''.join(w for w in words if w!='-'),'notes':[
            {'at':str(i),'dur':'1','pitch':60+i,'lyrics':word} for i,word in enumerate(words)]}]}]}


def test_exact_plan_preserves_continuation_and_never_claims_listening():
    p=song();before=deepcopy(p.data)
    report=audit(p.data,plan(),require_full=True)
    assert report['planMatches'] and report['allProjectNotesMapped']
    assert report['exactlyMappedNotes']==3 and p.data==before
    assert not report['originalScoreIndependentlyVerified']
    assert not report['computedPhonemesVerified'] and not report['subjectiveListeningVerified']


def test_wrong_syllable_anchor_is_caught_even_when_text_and_note_count_match():
    report=audit(song(('山','河','-')).data,plan())
    assert not report['planMatches'] and report['phrases'][0]['actualText']=='山河'
    assert any(e['code']=='note_mapping_mismatch' for e in report['errors'])


def test_copying_first_verse_into_second_is_located():
    p=song(('山','河','山','河'));expected=plan(('山','河','天','地'))
    report=audit(p.data,expected)
    assert not report['planMatches']
    error=next(e for e in report['errors'] if e['code']=='text_mismatch')
    assert error['track']=='#1' and error['phrase']=='verse-1'
    assert error['actual']=='山河山河' and error['expected']=='山河天地'


def test_text_only_cannot_prove_note_mapping():
    expected=plan();del expected['tracks'][0]['phrases'][0]['notes']
    assert not audit(song().data,expected)['planMatches']
    report=audit(song().data,expected,text_only=True)
    assert report['planMatches'] and not report['allProjectNotesMapped'] and report['exactlyMappedNotes']==0
    assert not audit(song().data,expected,text_only=True,require_full=True)['planMatches']


def test_unselected_track_is_not_silently_accepted_as_full_project():
    p=song();t=deepcopy(p.data['tracks'][0]);t['name']='Other';p.data['tracks'].append(t)
    report=audit(p.data,plan(),require_full=True)
    assert not report['planMatches'] and report['projectAudibleNotes']==6
    assert report['errors'][-1]=={'code':'unmapped_project_notes','count':3}


def test_offsets_and_library_references_are_applied():
    p=song();t=p.data['tracks'][0];g=deepcopy(t['mainGroup']);g['uuid']='shared'
    p.data['library'].append(g);t['mainGroup']['notes']=[]
    r=empty_ref(g);r['blickOffset']=4*Q;r['pitchOffset']=-12;t['groups']=[r]
    expected=plan();phrase=expected['tracks'][0]['phrases'][0];phrase.update(start='4',end='7')
    for n in phrase['notes']:n['at']=str(int(n['at'])+4);n['pitch']-=12
    assert audit(p.data,expected,require_full=True)['planMatches']


def test_phrase_cannot_start_inside_sustain():
    expected=plan();expected['tracks'][0]['phrases'][0].update(start='1/2',text='河')
    del expected['tracks'][0]['phrases'][0]['notes']
    report=audit(song().data,expected,text_only=True)
    assert any(e['code']=='phrase_cuts_sustain' for e in report['errors'])


def test_orphan_continuation_and_empty_lyrics_fail():
    assert any(e['code']=='orphan_continuation' for e in audit(song(('-','山')).data,plan(('-','山')))['errors'])
    assert any(e['code']=='empty_lyric' for e in audit(song(('', '山')).data,plan(('', '山')))['errors'])


def test_phoneme_override_is_compared_only_when_explicit():
    p=song();p.data['tracks'][0]['mainGroup']['notes'][0]['phonemes']='wrong'
    assert audit(p.data,plan())['planMatches']
    expected=plan();expected['tracks'][0]['phrases'][0]['notes'][0]['phonemes']='expected'
    assert not audit(p.data,expected)['planMatches']


@pytest.mark.parametrize('mutate',[
    lambda p:p.update(unknown=True),
    lambda p:p['tracks'][0]['phrases'][0].update(start=True),
    lambda p:p['tracks'][0]['phrases'][0].update(end='1/100000000000'),
    lambda p:p['tracks'][0]['phrases'][0].update(text='wrong plan'),
    lambda p:p['tracks'][0]['phrases'].append(deepcopy(p['tracks'][0]['phrases'][0])),
    lambda p:p['tracks'].append(deepcopy(p['tracks'][0])),
])
def test_invalid_plans_are_rejected(mutate):
    expected=plan();mutate(expected)
    with pytest.raises((ValueError,TypeError)):audit(song().data,expected)


def test_cli_failure_is_nonzero_readonly_and_batch_stops(tmp_path):
    src=tmp_path/'song.svp';song().save(src);expected=tmp_path/'plan.json'
    expected.write_text(json.dumps(plan(('山','河','-'))),encoding='utf8')
    before=src.read_bytes();plan_before=expected.read_bytes();output=tmp_path/'report.json'
    assert main(['lyrics-check',str(src),'--plan',str(expected),'-o',str(output)])==2
    assert not json.loads(output.read_text('utf8'))['valid']
    assert src.read_bytes()==before and expected.read_bytes()==plan_before
    assert main(['lyrics-check',str(src),'--plan',str(expected),'-o',str(expected),'--force'])==2
    assert expected.read_bytes()==plan_before
    batch=tmp_path/'batch.json';never=tmp_path/'never.svp'
    batch.write_text(json.dumps([['lyrics-check',str(src),'--plan',str(expected)],['new','-o',str(never)]]),'utf8')
    result=execute(_parser().parse_args(['batch',str(batch)]))
    assert not result['valid'] and len(result['jobs'])==1 and not never.exists()


@pytest.mark.parametrize('reviewed,words',[(False,('山','-','河')),(True,('山','河','-'))])
def test_render_gate_fails_before_any_plugin_loading(tmp_path,monkeypatch,reviewed,words):
    import sv2cli.render
    called=[];monkeypatch.setattr(sv2cli.render,'render',lambda *a,**k:called.append(True))
    src=tmp_path/'song.svp';song().save(src);expected=plan(words);expected['source']['reviewed']=reviewed
    path=tmp_path/'plan.json';path.write_text(json.dumps(expected),'utf8');out=tmp_path/'output.wav'
    assert main(['render',str(src),'-o',str(out),'--lyrics-plan',str(path)])==2
    assert not called and not out.exists()


def test_valid_render_plan_propagates_evidence_without_claiming_sung_words(tmp_path,monkeypatch):
    import sv2cli.render
    monkeypatch.setattr(sv2cli.render,'render',lambda *a,**k:{'status':'mocked-no-audio'})
    src=tmp_path/'song.svp';song().save(src);path=tmp_path/'plan.json';path.write_text(json.dumps(plan()),'utf8')
    result=execute(_parser().parse_args(['render',str(src),'-o',str(tmp_path/'a.wav'),'--lyrics-plan',str(path)]))
    assert result['lyricPlanVerification']['allProjectNotesMapped']
    assert not result['lyricPlanVerification']['subjectiveListeningVerified']


@pytest.mark.parametrize('operation',['lyrics.set','phonemes.set'])
def test_positional_text_uses_performed_time_across_groups(operation):
    p=song(('old','old','old'));t=p.data['tracks'][0]
    # Main group is stored first but occurs last. Library notes themselves are unsorted.
    t['mainGroup']['notes']=t['mainGroup']['notes'][2:]
    g=empty_group();g['notes']=deepcopy(song(('old','old')).data['tracks'][0]['mainGroup']['notes'][::-1])
    p.data['library'].append(g);t['groups']=[empty_ref(g)];p.update_ranges()
    q=apply(p,[{'op':operation,'tracks':['#1'],'values':['山','-','河']}],True)
    field='lyrics' if operation=='lyrics.set' else 'phonemes'
    assert [n[field] for n in sorted(q.notes(),key=lambda n:n['onset'])]==['山','-','河']
    assert q.edit_report[0]['ordering']=='absolute-onset'
    assert [n['onset'] for n in q.edit_report[0]['noteOrder']]==[0,Q,2*Q]


def test_positional_text_rejects_multiple_tracks_and_simultaneous_notes():
    p=song(('山','河'));p.data['tracks'].append(empty_track('Other'));p.update_ranges()
    with pytest.raises(SVError,match='exactly one track'):apply(p,[{'op':'lyrics.set','values':['天','地']}],True)
    p=song(('山','河'));p.data['tracks'][0]['mainGroup']['notes'][1]['onset']=0;p.update_ranges()
    with pytest.raises(SVError,match='Simultaneous'):apply(p,[{'op':'lyrics.set','values':['天','地']}],True)
