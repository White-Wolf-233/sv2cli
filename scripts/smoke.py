"""Installation smoke test; does not require the licensed audio plugin."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix="sv2cli-smoke-") as folder:
    p=Path(folder)/"中文 project.svp"
    commands=[["new","--name","Example","-o",str(p)],["validate",str(p)],["inspect",str(p)],["doctor"],["capabilities"]]
    for args in commands:
        result=subprocess.run([sys.executable,"-m","sv2cli",*args],capture_output=True,text=True,encoding="utf8")
        if result.returncode:raise RuntimeError(result.stderr)
        json.loads(result.stdout)
print("Installation smoke test passed")
