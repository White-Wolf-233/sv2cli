"""A local, session-scoped mailbox for the official Lua scripting API."""
from importlib.resources import files
import json
import os
from pathlib import Path
import re
import time
import uuid
from .config import config_path, data_roots
from .errors import SVError
from .io import read_json, write_json, write_new

METHODS={"host.info","project.summary","notes.list","computed.phonemes","computed.pitch","playback.status","playback.play","playback.stop","playback.pause","playback.seek","retake.generate","retake.activate"}

def mailbox_path(root=None,session="default"):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",session):raise SVError("Session must be 1-64 letters, digits, _ or -")
    return Path(root or os.environ.get("SV2CLI_MAILBOX") or config_path().parent/"mailbox").expanduser().resolve()/session

def install(scripts_dir=None,mailbox=None,session="default"):
    candidates=[p/"scripts" for p in data_roots()]
    target=Path(scripts_dir).expanduser() if scripts_dir else next((p for p in candidates if p.exists()),None)
    if target is None:raise SVError("Specify --scripts-dir for this Synthesizer V installation")
    box=mailbox_path(mailbox,session);box.mkdir(parents=True,exist_ok=True)
    json_lua=files("sv2cli").joinpath("assets/json.lua").read_text("utf8")
    bridge=files("sv2cli").joinpath("assets/bridge.lua").read_text("utf8")
    # JSON string escaping is also valid for Lua paths except \u escapes. Paths
    # remain literal UTF-8, and JSON supplies quote/backslash/control escaping.
    literal=json.dumps(str(box),ensure_ascii=False)
    script="local json = (function()\n"+json_lua+"\nend)()\nlocal MAILBOX = "+literal+"\n"+bridge
    name=f"sv2cli-{session}.lua";path=target/name
    # Installing an identical script is idempotent. Changed scripts get an
    # automatic timestamped backup, never overwrite an unrelated script.
    if path.exists() and path.read_text("utf8")==script:return {"script":str(path),"mailbox":str(box),"unchanged":True}
    if path.exists():write_new(path.with_suffix(f".{time.time_ns()}.bak"),path.read_bytes())
    write_new(path,script,force=True)
    return {"script":str(path),"mailbox":str(box),"nextStep":"In Synthesizer V: Scripts > Rescan, then run sv2cli bridge once. Live requests need the bridge running; offline commands and VST3 renders do not."}

def call(method,args,mailbox=None,session="default",timeout=10):
    if method not in METHODS:raise SVError(f"Unknown live method {method}; supported: {sorted(METHODS)}")
    if not isinstance(args,dict) or timeout<=0:raise SVError("Live args must be an object and timeout positive")
    box=mailbox_path(mailbox,session);box.mkdir(parents=True,exist_ok=True)
    lock=box/"client.lock"
    try:lock.mkdir()
    except FileExistsError as e:raise SVError("Another client owns this session. Do not retry a timed-out mutation; inspect the host first.","session_busy") from e
    request_id=uuid.uuid4().hex
    req=box/"request.json";response=box/f"response-{request_id}.json"
    try:
        if req.exists():raise SVError("Pending request exists. Inspect the session before submitting another request.","session_busy")
        arguments=dict(args)
        expected=arguments.pop("expectedProject",None)
        write_json(req,{"id":request_id,"method":method,"args":arguments,"expiresAt":time.time()+timeout,"expectedProject":expected})
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if response.exists():
                result=read_json(response)
                if result.get("id")!=request_id:raise SVError("Bridge response ID mismatch","protocol_error")
                if not result.get("ok"):raise SVError(result.get("error","Live API failed"),"live_failed")
                return result
            time.sleep(.05)
        raise SVError("Bridge timed out. Start the installed script in Studio. A submitted mutation may have executed; inspect before retrying.","live_timeout")
    finally:
        if req.exists():
            try:
                if read_json(req).get("id")==request_id:req.unlink()
            except SVError:pass
        if response.exists():response.unlink()
        lock.rmdir()
