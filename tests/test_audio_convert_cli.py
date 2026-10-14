import json
import math
import struct
import wave
import pytest
import subprocess,sys,os
from sv2cli.audio import check
from sv2cli.cli import main
from sv2cli.convert import midi_export,midi_import,csv_export,csv_import
from sv2cli.project import Project
from sv2cli.errors import SVError

@pytest.mark.parametrize('typ,bits',[(1,8),(1,16),(1,24),(1,32),(3,32),(3,64)])
def test_vector_validation_matches_dependency_free_path_across_second_boundaries(tmp_path,monkeypatch,typ,bits):
    np=pytest.importorskip('numpy')
    from sv2cli import audio
    rate=12000;channels=2
    values=np.zeros(rate*channels*3,dtype=np.float64)
    values[:channels*rate]=.25
    values[channels*rate*2:]=-.75
    values[-2]=1;values[-1]=-1
    if typ==3:
        values[channels*rate+1]=float('nan');values[channels*rate+2]=float('inf')
        payload=values.astype('<f4' if bits==32 else '<f8').tobytes()
    elif bits==8:payload=np.clip(values*128+128,0,255).astype(np.uint8).tobytes()
    else:
        scale=1<<(bits-1);ints=np.clip(values*scale,-scale,scale-1).astype(np.int64)
        payload=b''.join(int(v).to_bytes(bits//8,'little',signed=True) for v in ints)
    align=channels*(bits//8)
    fmt=struct.pack('<HHIIHH',typ,channels,rate,rate*align,align,bits)
    body=b'fmt '+struct.pack('<I',len(fmt))+fmt+b'data'+struct.pack('<I',len(payload))+payload
    path=tmp_path/'formats.wav';path.write_bytes(b'RIFF'+struct.pack('<I',len(body)+4)+b'WAVE'+body)
    fast=audio.check(path)
    monkeypatch.setattr(audio,'_numpy',lambda:None)
    slow=audio.check(path)
    assert fast['rms']==pytest.approx(slow.pop('rms'),rel=1e-12)
    fast.pop('rms')
    assert fast==slow

def test_empty_and_silent_audio_fail(tmp_path):
    for name,frames in [("empty",b""),("silent",b"\0"*400)]:
        p=tmp_path/(name+".wav")
        with wave.open(str(p),"wb") as f:f.setparams((1,2,8000,0,"NONE","none"));f.writeframes(frames)
        assert not check(p)["valid"]

def test_nonzero_audio_and_duration(tmp_path):
    p=tmp_path/"signal.wav"
    with wave.open(str(p),"wb") as f:
        f.setparams((1,2,8000,0,"NONE","none"));f.writeframes(b"".join(struct.pack("<h",round(10000*math.sin(i*.1))) for i in range(8000)))
    r=check(p)
    assert r["valid"] and r["durationSeconds"]==1
    assert "too_short" in check(p,expected_seconds=2)["failures"]

def test_midi_roundtrip_notes(project,tmp_path):
    midi=tmp_path/"p.mid";svp=tmp_path/"roundtrip.svp"
    midi_export(project,midi);midi_import(midi,svp)
    q=Project.load(svp)
    keys=["onset","duration","pitch","lyrics"]
    assert [[n[k] for k in keys] for n in q.notes()]==[[n[k] for k in keys] for n in project.notes()]

def test_midi_rejects_timing_rounding(project,tmp_path):
    project.data["tracks"][0]["mainGroup"]["notes"][0]["onset"]=1
    with pytest.raises(SVError):midi_export(project,tmp_path/"p.mid")

def test_csv_roundtrip(project,tmp_path):
    csv=tmp_path/"notes.csv";out=tmp_path/"out.svp"
    csv_export(project,csv);csv_import(csv,project,"#1",out)
    assert Project.load(out).score_fingerprint()==project.score_fingerprint()

def test_cli_source_protection(project,tmp_path,capsys):
    path=tmp_path/"p.svp";project.save(path);before=path.read_bytes()
    assert main(["voice",str(path),"-o",str(path),"--force","--params",'{"paramGender":0.2}'])==2
    assert path.read_bytes()==before
    assert "source_protected" in capsys.readouterr().err

@pytest.mark.parametrize("command",["notes","convert"])
def test_queries_and_conversions_also_protect_source(project,tmp_path,command,capsys):
    path=tmp_path/"p.svp";project.save(path);before=path.read_bytes()
    args=[command,str(path),"-o",str(path),"--force"]
    if command=="convert":args.insert(1,"csv-out")
    assert main(args)==2
    assert path.read_bytes()==before

def test_midi_chinese_track_names_and_lyrics(project,tmp_path):
    project.data["tracks"][0]["name"]="测试声部"
    project.data["tracks"][0]["mainGroup"]["notes"][0]["lyrics"]="啊"
    path=tmp_path/"notes.mid";out=tmp_path/"out.svp"
    midi_export(project,path);midi_import(path,out)
    q=Project.load(out)
    assert q.data["tracks"][0]["name"]=="测试声部" and q.notes()[0]["lyrics"]=="啊"

def test_cli_json_error_and_exit(capsys):
    assert main(["inspect","does-not-exist.svp"])==2
    assert json.loads(capsys.readouterr().err)["error"]["code"]=="invalid_file"

def test_cli_utf8_under_legacy_windows_pipe_encoding(tmp_path):
    env=dict(os.environ,PYTHONIOENCODING="cp1252")
    path=tmp_path/"中文.svp"
    r=subprocess.run([sys.executable,"-m","sv2cli","new","-o",str(path)],capture_output=True,env=env)
    assert r.returncode==0
    assert "中文" in json.loads(r.stdout.decode("utf8"))["output"]

def test_dry_run_writes_nothing(project,tmp_path,capsys):
    path=tmp_path/"p.svp";recipe=tmp_path/"recipe.json";out=tmp_path/"out.svp"
    project.save(path);recipe.write_text('[{"op":"mixer.set","values":{"pan":0.2}}]')
    assert main(["edit",str(path),"--recipe",str(recipe),"-o",str(out),"--dry-run"])==0
    assert not out.exists()
