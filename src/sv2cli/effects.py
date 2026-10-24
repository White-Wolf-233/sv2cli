"""Supported effect payloads. Unknown vendor extensions remain accessible via JSON Patch."""
from .errors import SVError
from .project import finite


def field(kind,minimum=None,maximum=None,unit=None,enum=None):
    return {k:v for k,v in dict(type=kind,minimum=minimum,maximum=maximum,unit=unit,enum=enum).items() if v is not None}


EQ={"freq":field('number',minimum=1,unit='Hz'),"gain":field('number',unit='dB'),"q":field('number',minimum=.001)}
SCHEMA={
    'room':{'enabled':field('boolean'),'positionX':field('number'),'positionY':field('number'),
            'size':field('number',minimum=.001),'reflectionGain':field('number')},
    'postRoomEq':{'enabled':field('boolean'),'filters':{'type':'array','items':EQ},'lowShelf':{'type':'object','properties':{k:v for k,v in EQ.items() if k!='q'}}},
    'compressor':{'enabled':field('boolean'),'attack':field('number',minimum=0),'ratio':field('number',minimum=1),'threshold':field('number',unit='dB')},
    'reverb':{'enabled':field('boolean'),'type':field('string',enum=['clean']),
              'preDelay':field('number',minimum=0,unit='seconds'),'decay':field('number',minimum=.001,unit='seconds'),
              'dryWetRatio':field('number',minimum=0,maximum=1)}
}


def _validate(value,spec,path):
    kind=spec['type']
    if kind=='boolean':
        if not isinstance(value,bool):raise SVError(f'{path} must be boolean')
    elif kind=='number':
        finite(value,path)
        if 'minimum' in spec and value<spec['minimum'] or 'maximum' in spec and value>spec['maximum']:
            raise SVError(f'{path} outside supported bounds: {spec}')
    elif kind=='string':
        if value not in spec['enum']:raise SVError(f'{path} must be one of {spec["enum"]}; other vendor values require an explicit JSON Patch')
    elif kind=='object':_object(value,spec['properties'],path)
    elif kind=='array':
        if not isinstance(value,list) or len(value)!=3:raise SVError(f'{path} must contain the three native EQ filters')
        for i,v in enumerate(value):_object(v,spec['items'],f'{path}[{i}]')


def _object(value,spec,path):
    if not isinstance(value,dict):raise SVError(f'{path} must be an object')
    if value.keys()-spec.keys():raise SVError(f'Unknown {path} fields: {sorted(value.keys()-spec.keys())}')
    for k,v in value.items():_validate(v,spec[k],f'{path}.{k}')


def validate(values):
    if not isinstance(values,dict) or not values:raise SVError('effects.set values must be a nonempty object')
    if values.keys()-SCHEMA.keys():raise SVError('Unknown effect; use room, postRoomEq, compressor, reverb')
    for name,value in values.items():_object(value,SCHEMA[name],name)
    return values
