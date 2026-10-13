from copy import deepcopy
import json
import pytest
from sv2cli.project import Project,QUARTER,empty_group,empty_ref,empty_track,difference
from sv2cli.edit import apply
from sv2cli.errors import SVError

def test_utf8_bom_and_nul(project,tmp_path):
    project.data["unknownFutureField"]={"诗":"你好","opaque":[2,3]}
    p=tmp_path/"中文.svp";p.write_bytes(b"\xef\xbb\xbf"+json.dumps(project.data,ensure_ascii=False).encode()+b"\0")
    result=Project.load(p)
    assert result.data==project.data

def test_absolute_offsets(project):
    t=project.data["tracks"][0];t["mainRef"]["blickOffset"]=7*QUARTER
    project.update_ranges()
    assert project.notes()[0]["onset"]==7*QUARTER
    assert t["mainRef"]["blickAbsoluteEnd"]==9*QUARTER
    assert project.validate()["valid"]

def test_conservative_repair(project):
    n=project.data["tracks"][0]["mainGroup"]["notes"][0]
    before=(n["pitch"],n["onset"],n["duration"],n["lyrics"])
    n["uuid"]="incorrect";n["musicalType"]="sing"
    project.data["tracks"][0]["mainRef"]["blickAbsoluteEnd"]=1
    assert not project.validate()["valid"]
    project.repair()
    assert project.validate()["valid"]
    assert (n["pitch"],n["onset"],n["duration"],n["lyrics"])==before

@pytest.mark.parametrize("field,value",[("pitch",-1),("pitch",128),("duration",0),("onset",.2),("pitch",float("nan"))])
def test_validation_rejects_invalid_notes(project,field,value):
    project.data["tracks"][0]["mainGroup"]["notes"][0][field]=value
    assert not project.validate()["valid"]

def test_flat_native_automation(project):
    project.data["tracks"][0]["mainGroup"]["parameters"]["loudness"]["points"]=[0,-10,QUARTER,0]
    assert project.validate()["valid"]

def test_odd_flat_automation_rejected(project):
    project.data["tracks"][0]["mainGroup"]["parameters"]["loudness"]["points"]=[0]
    assert not project.validate()["valid"]

def test_tempo_integration(project):
    project.data["time"]["tempo"]=[{"position":0,"bpm":120},{"position":QUARTER,"bpm":60}]
    assert project.seconds(2*QUARTER)==1.5

def test_integer_float_host_normalization_does_not_change_score(project):
    q=project.copy()
    q.data["time"]["startTimeSeconds"]=0.0
    q.data["time"]["tempo"][0]["bpm"]=120.0
    assert q.score_fingerprint()==project.score_fingerprint()

def test_track_indices_never_guess_names(project):
    project.data["tracks"].append(deepcopy(project.data["tracks"][0]))
    with pytest.raises(SVError):project.tracks(["Lead"])
    assert project.tracks(["#2"])[0][0]==1
    for bad in ["#0","#-1","#3","#bad"]:
        with pytest.raises(SVError):project.tracks([bad])

def test_no_clobber(project,tmp_path):
    path=tmp_path/"p.svp";project.save(path);before=path.read_bytes()
    with pytest.raises(SVError):project.save(path)
    assert path.read_bytes()==before

def test_fingerprint_mixer_vs_score(project):
    q=apply(project,[{"op":"mixer.set","values":{"gainDecibel":-3}}])
    assert difference(project,q)["scoreAndTimingIdentical"]
    q=apply(project,[{"op":"notes.transpose","semitones":1}],True)
    assert not difference(project,q)["scoreAndTimingIdentical"]
