"""Single-pass direct VST3 transport, loaded only inside the owned worker."""
import ctypes
import json
import os
from pathlib import Path
from fractions import Fraction
from .errors import SVError
from .project import Project, QUARTER
from .plugin_state import read_project, replace_project


def library_path(config):
    value=os.environ.get('SV2CLI_NATIVE_HOST') or config.get('native_host')
    if not value or not Path(value).expanduser().is_file():
        raise SVError('Build native/ and set SV2CLI_NATIVE_HOST or profile.native_host to the transport library. The drifting DawDreamer path is not used as a fallback.', 'native_host_missing')
    return str(Path(value).expanduser().resolve())


def clock_maps(project, rate):
    if project.data.get('time',{}).get('startTimeSeconds',0)!=0:
        raise SVError('Direct transport currently requires startTimeSeconds=0; no implicit score offset is applied.', 'unsupported_clock_origin')
    tempo=[{'sample':round(project.seconds(m['position'])*rate),
            'quarter':m['position']/QUARTER,'bpm':m['bpm']}
           for m in project.data['time']['tempo']]
    meter=[];q=Fraction(0);previous_index=0;bar=Fraction(4)
    for m in project.data['time']['meter']:
        q+=(m['index']-previous_index)*bar
        meter.append({'sample':round(project.seconds(round(q*QUARTER))*rate),
                      'quarter':float(q),'index':m['index'],
                      'numerator':m['numerator'],'denominator':m['denominator']})
        previous_index=m['index'];bar=Fraction(m['numerator']*4,m['denominator'])
    for values in (tempo,meter):
        if not values or values[0]['sample']!=0 or any(b['sample']<=a['sample'] for a,b in zip(values,values[1:])):
            raise SVError('Clock marks collide at the requested sample resolution','unsupported_clock_resolution')
    return tempo,meter


def verify_tuning(requested,loaded):
    """Reject a plugin that silently ignores explicitly requested SV2 pitch edits."""
    import math
    def equivalent(a,b):
        if isinstance(a,(int,float)) and not isinstance(a,bool):
            return isinstance(b,(int,float)) and not isinstance(b,bool) and math.isclose(a,b,rel_tol=1e-5,abs_tol=1e-5)
        if isinstance(a,list):return isinstance(b,list) and len(a)==len(b) and all(equivalent(x,y) for x,y in zip(a,b))
        if isinstance(a,dict):return isinstance(b,dict) and all(k in b and equivalent(v,b[k]) for k,v in a.items())
        return a==b
    loaded_groups={g['uuid']:g for _,t in loaded.tracks() for _,g in loaded.references(t)}
    count=0
    for ti,t in requested.tracks():
        fx=t.get('mixer',{}).get('fxParams',{})
        if fx and not equivalent(fx,loaded.data['tracks'][ti].get('mixer',{}).get('fxParams',{})):
            raise SVError(f'Plugin did not preserve requested effects on track {ti+1}; values may be unsupported or clamped','effect_load_mismatch')
        for _,g in requested.references(t):
            actual=loaded_groups.get(g['uuid'],{})
            if g.get('pitchControls') and not equivalent([{k:v for k,v in c.items() if k!='id'} for c in g['pitchControls']],
                                                       [{k:v for k,v in c.items() if k!='id'} for c in actual.get('pitchControls',[])]):
                raise SVError(f'Plugin did not preserve requested pitch controls in group {g["uuid"]}','tuning_load_mismatch')
            actual_notes={n.get('uuid'):n for n in actual.get('notes',[])}
            for n in g.get('notes',[]):
                attrs={k:v for k,v in n.get('attributes',{}).items() if k in {'expValueX','expValueY','dF0VbrMod'}}
                if attrs:
                    if not equivalent(attrs,actual_notes.get(n.get('uuid'),{}).get('attributes',{})):
                        raise SVError(f'Plugin did not preserve requested expression on note {n.get("uuid")}','tuning_load_mismatch')
                    count+=1
    return count


def render_once(job,project,event):
    work=Path(job['work']);tempo,meter=clock_maps(project,job['sampleRate'])
    request={**job,'tempoSegments':tempo,'meterSegments':meter,'bufferSize':job.get('bufferSize',512)}
    try:library=ctypes.CDLL(job['nativeHost'])
    except OSError as e:raise SVError(f'Cannot load native transport: {e}','native_host_load_failed') from e
    if library.sv2cli_transport_abi_version()!=1:
        raise SVError('Unsupported native transport ABI','native_host_version')
    callback_type=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_char_p)
    errors=[];native_errors=[];loaded_verified=False;started=False;completed=False
    def receive(raw):
        nonlocal loaded_verified,started,completed
        try:
            value=json.loads(raw.decode('utf8'));kind=value.pop('event')
            if kind=='native_state_required':
                base=(work/'native-base-state.bin').read_bytes()
                (work/'native-project-state.bin').write_bytes(replace_project(base,project.data))
            elif kind=='native_loaded_score_ready':
                loaded=Project(read_project((work/'loaded-state.bin').read_bytes()))
                if loaded.score_fingerprint()!=project.score_fingerprint():
                    raise SVError('Plugin did not load the requested score','project_load_mismatch')
                verify_tuning(project,loaded)
                loaded_verified=True
            elif kind=='native_error':native_errors.append(value.get('message','Native transport failed'))
            elif kind=='native_single_pass':
                if not loaded_verified:raise SVError('Playback started before score verification','native_protocol_error')
                if started or value.get('renderPasses')!=1:
                    raise SVError('Native host attempted more than one render pass','render_retries_disabled')
                started=True
            elif kind=='native_render_complete':
                if not started or completed:raise SVError('Invalid native completion sequence','native_protocol_error')
                completed=True
            event(kind,**value);return 0
        except Exception as e:
            if not errors:errors.append(e)
            return 1
    callback=callback_type(receive)
    library.sv2cli_transport_render.argtypes=[ctypes.c_char_p,callback_type]
    library.sv2cli_transport_render.restype=ctypes.c_int
    status=library.sv2cli_transport_render(json.dumps(request,ensure_ascii=False,allow_nan=False).encode('utf8'),callback)
    if errors:raise errors[0]
    if status:raise SVError(native_errors[-1] if native_errors else 'Native transport failed','native_render_failed')
    if not loaded_verified:raise SVError('Native transport did not verify loaded score','project_load_mismatch')
    if not completed:raise SVError('Native transport did not complete its single pass','native_protocol_error')
    return {'transport':'direct-vst3-sample-clock','renderPasses':1,
            'automaticRetries':False,'audioTranslated':False,'resampled':False,
            'tempoSegments':tempo,'meterSegments':meter,'loadedScoreVerified':True,'loadedTuningVerified':True}
