import os
import platform
import shutil
import sys
from pathlib import Path
from .io import read_json, write_json
from .errors import SVError

def config_path():
    if os.environ.get("SV2CLI_CONFIG"):
        return Path(os.environ["SV2CLI_CONFIG"]).expanduser()
    if sys.platform == "win32":
        base=Path(os.environ.get("APPDATA",Path.home()/"AppData/Roaming"))
    elif sys.platform == "darwin":
        base=Path.home()/"Library/Application Support"
    else:
        base=Path(os.environ.get("XDG_CONFIG_HOME",Path.home()/".config"))
    return base/"sv2cli"/"config.json"

def data_roots():
    if sys.platform == "win32":
        return [Path(os.environ.get("APPDATA",Path.home()/"AppData/Roaming"))/"Dreamtonics/Synthesizer V Studio 2"]
    if sys.platform == "darwin":
        return [Path.home()/"Library/Application Support/Dreamtonics/Synthesizer V Studio 2",Path("/Library/Application Support/Dreamtonics/Synthesizer V Studio 2")]
    return [Path.home()/".config/Dreamtonics/Synthesizer V Studio 2"]

def plugin_candidates():
    if sys.platform == "win32":
        return [Path(os.environ.get("COMMONPROGRAMFILES","C:/Program Files/Common Files"))/"VST3/Synthesizer V Studio 2 Plugin.vst3"]
    if sys.platform == "darwin":
        return [Path("/Library/Audio/Plug-Ins/VST3/Synthesizer V Studio 2 Plugin.vst3"),Path.home()/"Library/Audio/Plug-Ins/VST3/Synthesizer V Studio 2 Plugin.vst3"]
    return []

def load_config():
    p=config_path()
    d=read_json(p) if p.exists() else {"profiles":{}}
    if not isinstance(d,dict) or not isinstance(d.get("profiles",{}),dict):
        raise SVError("Invalid config: profiles must be an object")
    return d

def profile(name="default"):
    d=load_config();p=d.get("profiles",{}).get(name,{})
    if name!="default" and name not in d.get("profiles",{}):
        raise SVError(f"Profile not found: {name}")
    p=dict(p)
    if os.environ.get("SV2CLI_PLUGIN"):
        p["plugin"]=os.environ["SV2CLI_PLUGIN"]
    p.setdefault("plugin",next((str(x) for x in plugin_candidates() if x.exists()),None))
    p.setdefault("data_roots",[str(x) for x in data_roots() if x.exists()])
    return p

def set_profile(name, value):
    if not name or not isinstance(value,dict):raise SVError("Profile needs a name and JSON object")
    d=load_config();d.setdefault("profiles",{})[name]=value
    return write_json(config_path(),d,force=True)

def catalog(roots):
    products=[];installations=[]
    for root in roots:
        root=Path(root).expanduser()
        for p in sorted((root/"databases/meta").glob("*.json")):
            try:
                d=read_json(p)
                if isinstance(d,dict) and d.get("name"):
                    products.append({"id":p.stem,"name":d["name"],"vendor":d.get("vendor"),"languages":d.get("languages",[]),"pitchRange":d.get("pitchRange"),"installed":"unverified", "source":str(p)})
            except SVError:
                continue
        db=root/"databases"
        if db.exists():
            for folder in sorted(db.iterdir()):
                if folder.is_dir() and folder.name not in {"meta","tmp"}:
                    installations.append({"id":folder.name,"versions":[p.name for p in folder.iterdir() if p.is_dir()],"path":str(folder)})
    return {"catalog":products,"installationDirectories":installations,"note":"Cached catalog entries are not proof of installation or activation. No license files are read."}

def doctor(name="default"):
    import importlib.util
    p=profile(name)
    deps={x:importlib.util.find_spec(x) is not None for x in ("dawdreamer","numpy","mido")}
    plugin=p.get("plugin")
    return {"platform":platform.platform(),"python":sys.version.split()[0],"profile":name,"configPath":str(config_path()),"plugin":plugin,"pluginExists":bool(plugin and Path(plugin).exists()),"dependencies":deps,"ffmpeg":shutil.which("ffmpeg"),"dataRoots":p.get("data_roots",[]),"offlineProjectTools":True,"renderReadyToAttempt":bool(plugin and Path(plugin).exists() and deps["dawdreamer"] and deps["numpy"]),"renderVerified":False,"note":"doctor detects prerequisites only; run an actual render to verify audio. SV2 native render supports Windows/macOS; Linux core tools and command backend are supported."}
