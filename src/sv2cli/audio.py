"""RIFF/WAVE validation, including float PCM and WAVE_FORMAT_EXTENSIBLE."""
import math
import struct
from pathlib import Path
from .errors import SVError

def check(path, expected_seconds=None, min_peak=1e-6, clipping_limit=0.001):
    path=Path(path)
    try:
        with path.open("rb") as f:
            header=f.read(12)
            if len(header)!=12 or header[:4]!=b"RIFF" or header[8:]!=b"WAVE":
                raise SVError("Expected RIFF/WAVE file", "invalid_audio")
            fmt=None;chunks=[]
            file_size=path.stat().st_size
            while f.tell()+8<=file_size:
                tag,size=struct.unpack("<4sI",f.read(8));pos=f.tell()
                if pos+size>file_size:
                    raise SVError("Truncated WAV chunk", "invalid_audio")
                if tag==b"fmt ":
                    b=f.read(size)
                    if len(b)<16:raise SVError("Invalid WAV format chunk", "invalid_audio")
                    typ,channels,rate,_,align,bits=struct.unpack("<HHIIHH",b[:16])
                    if typ==65534 and len(b)>=40:typ=struct.unpack("<H",b[24:26])[0]
                    fmt=(typ,channels,rate,align,bits)
                elif tag==b"data":chunks.append((pos,size))
                f.seek(pos+size+(size&1))
            if fmt is None or not chunks:raise SVError("WAV lacks fmt or data", "invalid_audio")
            typ,channels,rate,align,bits=fmt
            if channels<1 or rate<1 or align!=channels*((bits+7)//8) or typ not in {1,3}:
                raise SVError("Unsupported WAV encoding", "unsupported_audio")
            if typ==1 and bits not in {8,16,24,32} or typ==3 and bits not in {32,64}:
                raise SVError("Unsupported WAV sample width", "unsupported_audio")
            count=nonzero=clipped=0;peak=total=0.0;invalid=0
            seconds_bins={};width=(bits+7)//8
            for pos,size in chunks:
                if size%align:raise SVError("Partial PCM frame", "invalid_audio")
                f.seek(pos);remaining=size
                while remaining:
                    b=f.read(min(remaining,align*16384));remaining-=len(b)
                    for i in range(0,len(b),width):
                        if typ==3:v=struct.unpack("<f" if bits==32 else "<d",b[i:i+width])[0]
                        elif bits==8:v=(b[i]-128)/128
                        else:v=int.from_bytes(b[i:i+width],"little",signed=True)/(1<<(bits-1))
                        if not math.isfinite(v):invalid+=1;v=0
                        av=abs(v);peak=max(peak,av);total+=v*v;nonzero+=av>min_peak;clipped+=av>=0.999
                        sec=int(count/channels/rate)
                        seconds_bins[sec]=max(seconds_bins.get(sec,0),av)
                        count+=1
            duration=count/channels/rate
            rms=math.sqrt(total/count) if count else 0
            failures=[]
            if count==0:failures.append("empty_audio")
            if peak<min_peak:failures.append("silent_audio")
            if invalid:failures.append("nonfinite_audio")
            clip_ratio=clipped/count if count else 0
            if clip_ratio>clipping_limit:failures.append("clipping")
            if expected_seconds is not None and duration+0.1<expected_seconds:failures.append("too_short")
            return {"path":str(path.resolve()),"valid":not failures,"failures":failures,"sampleRate":rate,"channels":channels,"bitDepth":bits,"encoding":"float" if typ==3 else "PCM", "frames":count//channels,"durationSeconds":duration,"peak":peak,"rms":rms,"nonzeroRatio":nonzero/count if count else 0,"clippedRatio":clip_ratio,"activeSeconds":[i for i,v in sorted(seconds_bins.items()) if v>min_peak]}
    except OSError as e:
        raise SVError(f"Cannot read audio: {e}", "invalid_audio") from e
