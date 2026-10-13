"""Adapt public JUCE/VST3 state, never inspect or patch an engine binary.

The SV2 component exposes a JSON envelope containing projectContent. We obtain
the envelope from the user's installed plugin, replace only the project fields,
and preserve all opaque bytes. Unknown layouts fail closed.
"""
import json
import struct
import xml.etree.ElementTree as ET
from .errors import SVError

ALPHABET=".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"

def decode_memory(text):
    try:
        length,enc=text.split(".",1);size=int(length)
        if size<0 or size>256*1024*1024 or len(enc)!=(size*8+5)//6:
            raise ValueError("Invalid encoded length")
        out=bytearray(size)
        # Decode in eight-character blocks (48 bits / six bytes).
        for i in range(0,len(enc),8):
            bits=sum(ALPHABET.index(c)<<(j*6) for j,c in enumerate(enc[i:i+8]))
            b=bits.to_bytes(6,"little");off=(i//8)*6
            out[off:min(size,off+6)]=b[:min(6,size-off)]
        return bytes(out)
    except (ValueError,TypeError,AttributeError) as e:
        raise SVError(f"Unsupported JUCE component state: {e}", "unsupported_plugin_state") from e

def encode_memory(data):
    chars=[]
    for i in range(0,len(data),6):
        chunk=data[i:i+6];v=int.from_bytes(chunk,"little")
        chars.extend(ALPHABET[(v>>(j*6))&63] for j in range((len(chunk)*8+5)//6))
    return str(len(data))+"."+"".join(chars)

def read_project(raw):
    try:
        root=ET.fromstring(raw[8:].rstrip(b"\0"))
        component=decode_memory(root.find("IComponent").text)
        obj,_=json.JSONDecoder().raw_decode(component.decode("utf8",errors="surrogateescape"))
        return json.loads(obj["projectContent"])
    except (ValueError,KeyError,AttributeError,ET.ParseError) as e:
        raise SVError(f"Cannot verify loaded plugin project: {e}","unsupported_plugin_state") from e

def replace_project(raw, project, project_path=""):
    if len(raw)<9 or raw[:4]!=b"VC2!":
        raise SVError("Plugin state is not the expected JUCE VST3 envelope", "unsupported_plugin_state")
    try:
        root=ET.fromstring(raw[8:].rstrip(b"\0"))
        elem=root.find("IComponent")
        if elem is None:raise ValueError("No IComponent")
        component=decode_memory(elem.text)
        # JSON is followed by opaque JUCE parameter data. UTF-8 decode only the
        # textual prefix and preserve the exact suffix, including non-UTF8 bytes.
        text=component.decode("utf8",errors="surrogateescape")
        envelope,end=json.JSONDecoder().raw_decode(text)
        if not isinstance(envelope,dict) or not isinstance(envelope.get("projectContent"),str) or "projectPath" not in envelope:
            raise ValueError("Unknown project envelope")
        suffix=component[len(text[:end].encode("utf8",errors="surrogateescape")):]
        envelope["projectContent"]=json.dumps(project,ensure_ascii=False,allow_nan=False)
        envelope["projectPath"]=project_path
        replacement=json.dumps(envelope,ensure_ascii=False,allow_nan=False).encode("utf8")+suffix
        elem.text=encode_memory(replacement)
        xml=ET.tostring(root,encoding="utf8",xml_declaration=True)
        return raw[:4]+struct.pack("<I",len(xml))+xml+b"\0"
    except (ValueError,ET.ParseError,UnicodeError) as e:
        raise SVError(f"Unknown plugin state layout: {e}", "unsupported_plugin_state") from e
