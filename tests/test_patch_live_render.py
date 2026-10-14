import json
import sys
import threading
import time
from pathlib import Path
import pytest
from sv2cli.edit import apply
from sv2cli.io import write_json
from sv2cli.live import call,install
from sv2cli.render import render
from sv2cli.errors import SVError

def test_patch_cannot_bypass_score_lock(project):
    op={"op":"json.patch","patch":[{"op":"replace","path":"/tracks/0/mainGroup/notes/0/pitch","value":72}]}
    with pytest.raises(SVError,match="score-lock"):apply(project,[op])
    assert apply(project,[op],True).notes()[0]["pitch"]==72

def test_patch_guarded_and_unknown_fields(project):
    op={"op":"json.patch","patch":[{"op":"test","path":"/version","value":196},{"op":"add","path":"/future~1field","value":{"text":"你好"}}]}
    assert apply(project,[op]).data["future/field"]["text"]=="你好"
    with pytest.raises(SVError):apply(project,[{"op":"json.patch","patch":[{"op":"test","path":"/version","value":999}]}])

def test_live_mailbox_response_and_lock(tmp_path):
    box=tmp_path/"default";box.mkdir()
    def host():
        req=box/"request.json"
        deadline=time.monotonic()+5
        while not req.exists() and time.monotonic()<deadline:time.sleep(.01)
        time.sleep(.05);r=json.loads(req.read_text())
        write_json(box/f"response-{r['id']}.json",{"id":r["id"],"ok":True,"result":{"pong":True}})
    t=threading.Thread(target=host);t.start()
    result=call("host.info",{},tmp_path,timeout=2);t.join()
    assert result["result"]["pong"]
    assert not (box/"client.lock").exists()

def test_live_timeout_does_not_leave_request(tmp_path):
    with pytest.raises(SVError,match="timed out"):call("host.info",{},tmp_path,timeout=.1)
    assert not (tmp_path/"default/request.json").exists()

def test_bridge_install_portable_and_idempotent(tmp_path):
    scripts=tmp_path/"中文 scripts";scripts.mkdir()
    r=install(scripts,tmp_path/"mailbox","test")
    script=Path(r["script"]).read_text("utf8")
    assert "function getClientInfo" in script and "中文" not in script  # script folder isn't embedded
    assert install(scripts,tmp_path/"mailbox","test")["unchanged"]
    assert len(list(scripts.glob("*.lua")))==1

def test_bridge_lua_syntax_and_read_dispatch(tmp_path):
    lupa=pytest.importorskip("lupa")
    scripts=tmp_path/"scripts";scripts.mkdir();r=install(scripts,tmp_path/"mailbox")
    lua=lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute('SV={}; function SV:getHostInfo() return {hostVersion="mock"} end; function SV:setTimeout(ms, fn) end')
    lua.execute(Path(r["script"]).read_text("utf8"))
    req=Path(r["mailbox"])/"request.json"
    write_json(req,{"id":"abc123","method":"host.info","args":{},"expiresAt":time.time()+10})
    lua.globals().main()
    reply=json.loads(req.with_name("response-abc123.json").read_text())
    assert reply["ok"] and reply["result"]["hostVersion"]=="mock"

def test_command_backend_real_process_and_audio_validation(project,tmp_path,monkeypatch):
    config=tmp_path/"config.json";monkeypatch.setenv("SV2CLI_CONFIG",str(config))
    script=tmp_path/"fake_backend.py"
    script.write_text('import sys,wave,math,struct,json\nfrom pathlib import Path\nj=json.loads(Path(sys.argv[2]).read_text());seconds=j["duration"];rate=j["sampleRate"];channels=j["channels"]\nwith wave.open(sys.argv[1],"wb") as f:\n f.setparams((channels,2,rate,0,"NONE","none"));f.writeframes(b"".join(struct.pack("<h",int(math.sin(i/10)*1000))*channels for i in range(round(rate*seconds))))\n')
    write_json(config,{"profiles":{"default":{"render_command":[sys.executable,str(script),"{output}","{job}"]}}})
    source=tmp_path/"project.svp";project.save(source);target=tmp_path/"audio.wav"
    result=render(source,target,backend="command",timeout=10)
    assert target.stat().st_size>44 and result["audio"][0]["valid"]
    assert result["backend"]=="command" and result["subjectiveListeningVerified"] is False
    with pytest.raises(SVError):render(source,target,backend="command")

def test_command_backend_rejects_silent_result(project,tmp_path,monkeypatch):
    config=tmp_path/"config.json";monkeypatch.setenv("SV2CLI_CONFIG",str(config))
    code='import sys,wave\nwith wave.open(sys.argv[1],"wb") as f:\n f.setparams((1,2,8000,0,"NONE","none"));f.writeframes(b"\\0"*48000)'
    write_json(config,{"profiles":{"default":{"render_command":[sys.executable,"-c",code,"{output}"]}}})
    source=tmp_path/"project.svp";project.save(source);target=tmp_path/"audio.wav"
    with pytest.raises(SVError,match="audio checks"):render(source,target,backend="command",timeout=10)
    assert not target.exists()
