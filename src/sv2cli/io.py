import json
import os
from pathlib import Path
import tempfile
from .errors import SVError

def read_json(path):
    try:
        # Native SVP saves can include a trailing NUL and a UTF-8 BOM.
        return json.loads(Path(path).read_text(encoding="utf-8-sig").rstrip("\0\r\n "))
    except (OSError, ValueError) as e:
        raise SVError(f"Cannot read JSON {path}: {e}", "invalid_file") from e

def write_new(path, content, force=False):
    """No clobber by default. A partial write is never presented as a result."""
    path = Path(path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode("utf-8")
    if path.exists() and not force:
        raise SVError(f"Output exists: {path}. Choose another name or use --force.", "output_exists")
    if not force:
        try:
            with path.open("xb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError as e:
            raise SVError(f"Output exists: {path}", "output_exists") from e
        except Exception:
            if path.exists():
                path.unlink()
            raise
    else:
        fd, tmp = tempfile.mkstemp(prefix=".sv2cli-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return str(path)

def write_json(path, value, force=False):
    return write_new(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", force)
