"""RFC 6902 JSON Patch for version-specific SVP fields."""
from copy import deepcopy
from .errors import SVError

def _tokens(pointer):
    if pointer=="":return []
    if not isinstance(pointer,str) or not pointer.startswith("/"):raise SVError("JSON Pointer must start with /")
    return [s.replace("~1","/").replace("~0","~") for s in pointer[1:].split("/")]

def _get(document,pointer):
    current=document
    for token in _tokens(pointer):
        if isinstance(current,list):
            if not token.isdigit() or token!=str(int(token)) or int(token)>=len(current):raise SVError("JSON Pointer array index out of range")
            current=current[int(token)]
        elif isinstance(current,dict) and token in current:current=current[token]
        else:raise SVError(f"JSON Pointer does not exist: {pointer}")
    return current

def patch(document,operations):
    if not isinstance(operations,list):raise SVError("JSON Patch must be an array")
    for item in operations:
        op=item.get("op");path=item.get("path");tokens=_tokens(path)
        if op=="test":
            if _get(document,path)!=item.get("value"):raise SVError(f"JSON Patch test failed: {path}")
            continue
        if op not in {"add","replace","remove","copy","move"}:raise SVError(f"Unsupported JSON Patch operation: {op}")
        value=deepcopy(item.get("value"))
        if op in {"copy","move"}:
            source=item.get("from")
            if op=="move" and (path==source or path.startswith(source+"/")):
                if path==source:continue
                raise SVError("Cannot move an object into its own descendant")
            value=deepcopy(_get(document,source))
            if op=="move":patch(document,[{"op":"remove","path":source}])
            op="add"
        if not tokens:raise SVError("Replacing/removing the project root is unsupported")
        parent=document
        for token in tokens[:-1]:
            parent=_get(parent,"/"+token.replace("~","~0").replace("/","~1"))
        token=tokens[-1]
        if isinstance(parent,list):
            if token=="-" and op=="add":parent.append(value);continue
            if not token.isdigit() or token!=str(int(token)):raise SVError("Invalid JSON Patch array index")
            i=int(token)
            if op=="add":
                if i>len(parent):raise SVError("JSON Patch array index out of range")
                parent.insert(i,value)
            else:
                if i>=len(parent):raise SVError("JSON Patch array index out of range")
                if op=="remove":parent.pop(i)
                else:parent[i]=value
        elif isinstance(parent,dict):
            if op!="add" and token not in parent:raise SVError(f"JSON Patch target does not exist: {path}")
            if op=="remove":del parent[token]
            else:parent[token]=value
        else:raise SVError("JSON Patch parent is not a container")
    return document
