from copy import deepcopy
import pytest
from sv2cli.edit import apply
from sv2cli.project import QUARTER,empty_group,empty_ref,empty_track
from sv2cli.errors import SVError

def test_transaction_failure_does_not_mutate_source(project):
    before=deepcopy(project.data)
    with pytest.raises(SVError):apply(project,[{"op":"mixer.set","values":{"pan":.3}},{"op":"voice.set","values":{"paramGender":10}}])
    assert project.data==before

@pytest.mark.parametrize("op",["notes.transpose","notes.shift","track.add","track.remove","tempo.set","lyrics.set","notes.update"])
def test_score_mutations_require_opt_in(project,op):
    with pytest.raises(SVError,match="changes the score"):apply(project,[{"op":op}])

def test_explicit_score_lock_overrides_opt_in(project):
    with pytest.raises(SVError,match="score-lock"):apply(project,[{"op":"notes.transpose","semitones":2}],True,True)

def test_voice_switch_removes_stale_group_overrides(project):
    t=project.data["tracks"][0];g=empty_group("shared");project.data["library"].append(g)
    t["groups"]=[empty_ref(g)];t["groups"][0]["database"]["name"]="Old Singer"
    db={"name":"New Singer","backendType":"SVR3","language":"english","version":"201"}
    q=apply(project,[{"op":"voice.switch","database":db}],score_lock=True)
    assert q.data["tracks"][0]["mainRef"]["database"]==db
    assert q.data["tracks"][0]["groups"][0]["database"]==db
    assert t["groups"][0]["database"]["name"]=="Old Singer"
    q=apply(project,[{"op":"voice.switch","database":db,"inherit":True}])
    assert q.data["tracks"][0]["groups"][0]["database"]["name"]==""
    assert q.data["tracks"][0]["groups"][0]["database"]["version"]=="-2"

def test_voice_switch_keeps_cross_language_pronunciation(project):
    r=project.data["tracks"][0]["mainRef"]
    r["database"].update(languageOverride="mandarin",phonesetOverride="xsampa")
    q=apply(project,[{"op":"voice.switch","database":{"name":"New Singer","backendType":"SVR3"}}])
    db=q.data["tracks"][0]["mainRef"]["database"]
    assert db["languageOverride"]=="mandarin" and db["phonesetOverride"]=="xsampa"

def test_mandarin_override_sets_matching_phoneset(project):
    q=apply(project,[{"op":"language.set","language":"mandarin"}])
    assert q.data["tracks"][0]["mainRef"]["database"]["phonesetOverride"]=="xsampa"

def test_copy_on_write_shared_group(project):
    t1=project.data["tracks"][0];g=deepcopy(t1["mainGroup"]);g["uuid"]="shared-group"
    t1["mainGroup"]["notes"]=[];t1["groups"]=[empty_ref(g)]
    t2=empty_track("Backing");t2["groups"]=[empty_ref(g)]
    project.data["library"].append(g);project.data["tracks"].append(t2);project.update_ranges()
    q=apply(project,[{"op":"notes.transpose","tracks":["#1"],"semitones":12}],True)
    assert [r["pitch"] for r in q.notes(["#1"]) ]==[72,74]
    assert [r["pitch"] for r in q.notes(["#2"]) ]==[60,62]
    assert q.data["tracks"][0]["groups"][0]["groupID"]!=q.data["tracks"][1]["groups"][0]["groupID"]

def test_automation_written_in_native_flat_format(project):
    q=apply(project,[{"op":"automation.set","parameter":"gender","points":[[QUARTER,.3],[0,.1]]}])
    assert q.data["tracks"][0]["mainGroup"]["parameters"]["gender"]["points"]==[0,.1,QUARTER,.3]

@pytest.mark.parametrize("value",[-2,2,float("inf"),True])
def test_invalid_pan(project,value):
    with pytest.raises(SVError):apply(project,[{"op":"mixer.set","values":{"pan":value}}])

def test_lyrics_exact_count(project):
    with pytest.raises(SVError):apply(project,[{"op":"lyrics.set","values":["la"]}],True)
    q=apply(project,[{"op":"lyrics.set","values":["a","b"]}],True)
    assert [n["lyrics"] for n in q.notes()]==["a","b"]

def test_clone_independent(project):
    q=apply(project,[{"op":"track.clone","tracks":["#1"],"name":"Double"}],True)
    assert q.validate()["valid"]
    assert q.data["tracks"][0]["mainGroup"]["uuid"]!=q.data["tracks"][1]["mainGroup"]["uuid"]

def test_activate_retake_checks_id(project):
    with pytest.raises(SVError,match="does not exist"):apply(project,[{"op":"retake.activate","id":99}])
    n=project.data["tracks"][0]["mainGroup"]["notes"][0]
    n["takes"]={"activeTakeId":0,"takes":[{"id":0},{"id":1}]}
    q=apply(project,[{"op":"retake.activate","id":1,"uuids":[n["uuid"]]}])
    assert q.data["tracks"][0]["mainGroup"]["notes"][0]["takes"]["activeTakeId"]==1

def test_unknown_fields_preserved(project):
    project.data["future"]={"thing":[1,2,3]}
    q=apply(project,[{"op":"voice.set","values":{"paramGender":.15,"choirNumStems":4}}],score_lock=True)
    assert q.data["future"]==project.data["future"]
