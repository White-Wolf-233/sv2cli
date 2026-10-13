import json
import struct
import xml.etree.ElementTree as ET
import pytest
from sv2cli.plugin_state import decode_memory,encode_memory,replace_project
from sv2cli.errors import SVError

@pytest.mark.parametrize("length",[0,1,2,3,5,6,7,12,19,1024])
def test_public_juce_codec_roundtrip(length):
    data=bytes((i*53)%256 for i in range(length))
    assert decode_memory(encode_memory(data))==data

def test_juce_known_vector():
    assert decode_memory("3.XkkV")==b"XYZ"

def test_state_replacement_preserves_opaque_bytes(project):
    suffix=b"\0\xff\x03opaque"
    component=json.dumps({"projectPath":"old","projectContent":"{}","custom":[1,2],"araBridgeEnabled":True}).encode()+suffix
    xml=b"<VST3PluginState><IComponent>"+encode_memory(component).encode()+b"</IComponent></VST3PluginState>"
    raw=b"VC2!"+struct.pack("<I",len(xml))+xml+b"\0"
    result=replace_project(raw,project.data)
    root=ET.fromstring(result[8:].rstrip(b"\0"));b=decode_memory(root.find("IComponent").text)
    assert b.endswith(suffix)
    obj,end=json.JSONDecoder().raw_decode(b.decode("utf8",errors="surrogateescape"))
    assert obj["custom"]==[1,2]
    assert obj["araBridgeEnabled"] is True
    assert json.loads(obj["projectContent"])==project.data

def test_unknown_plugin_state_rejected(project):
    with pytest.raises(SVError):replace_project(b"unexpected",project.data)
