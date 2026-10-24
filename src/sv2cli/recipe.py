"""Validate operation envelopes before any edit; do not silently ignore typos."""
from .errors import SVError

FILTERS = {'tracks', 'groups', 'uuids', 'start', 'end', 'references'}
SPECS = {
    'voice.switch': ({'database'}, {'inherit','clearDictionary','keepLanguageOverride','tracks'}),
    'voice.set': ({'values'}, {'scope','tracks'}),
    'language.set': ({'language'}, {'phoneset','tracks'}),
    'dictionary.set': ({'dictionary'}, {'tracks'}),
    'mixer.set': ({'values'}, {'tracks'}), 'effects.set': ({'values'}, {'tracks'}),
    'track.rename': ({'name','tracks'}, set()), 'track.set': ({'values'}, {'tracks'}),
    'track.add': (set(), {'name'}), 'track.remove': ({'tracks'}, set()),
    'track.clone': ({'tracks'}, {'name'}), 'notes.replace': ({'notes'}, {'tracks'}),
    'notes.update': ({'values'}, FILTERS), 'notes.transpose': ({'semitones'}, FILTERS),
    'notes.shift': ({'blick'}, FILTERS), 'lyrics.set': ({'values'}, FILTERS),
    'phonemes.set': ({'values'}, FILTERS),
    'group.shift': ({'blick'}, {'tracks','groups','references'}),
    'group.transpose': ({'semitones'}, {'tracks','groups','references'}),
    'group.remove': ({'groups'}, {'tracks','references'}),
    'automation.set': ({'parameter','points'}, {'tracks','groups','references','mode'}),
    'pitch.controls': ({'controls'}, {'tracks','groups','references'}),
    'notes.expression': ({'preset'}, FILTERS | {'vibrato'}),
    'pitch.flatten': (set(), FILTERS | {'transitionMs','replaceControls'}),
    'notes.articulate': ({'gapMs'}, FILTERS),
    'retake.activate': ({'id'}, {'tracks','groups','uuids','references'}),
    'tempo.set': ({'marks'}, set()), 'meter.set': ({'marks'}, set()),
    'render.configure': ({'values'}, set()), 'json.patch': ({'patch'}, set()),
}

def validate_recipe(operations):
    if not isinstance(operations, list) or not all(isinstance(o, dict) for o in operations):
        raise SVError('Recipe must be an array of operation objects', 'invalid_recipe')
    for i, op in enumerate(operations):
        name = op.get('op')
        if not isinstance(name, str) or name not in SPECS:
            raise SVError(f'Operation {i+1}: unknown operation {name!r}', 'unsupported_operation')
        required, optional = SPECS[name]
        missing, unknown = required - op.keys(), op.keys() - required - optional - {'op'}
        if missing or unknown:
            raise SVError(f'Operation {i+1} ({name}): missing {sorted(missing)}; unknown {sorted(unknown)}', 'invalid_recipe')
        for key in ('tracks','groups','uuids','references'):
            if key in op and op[key] is not None:
                if not isinstance(op[key], list) or not op[key] or not all(isinstance(s,str) and s for s in op[key]):
                    raise SVError(f'{key} must be a nonempty array of strings', 'invalid_recipe')
        if 'scope' in op and op['scope'] not in {'main','all'}:
            raise SVError('scope must be main or all', 'invalid_recipe')
        for key in ('inherit','clearDictionary','keepLanguageOverride'):
            if key in op and not isinstance(op[key],bool):
                raise SVError(f'{key} must be boolean', 'invalid_recipe')
    return operations

def schema():
    from .effects import SCHEMA
    return {'operations': {name: {'required':sorted(req), 'optional':sorted(opt)} for name,(req,opt) in SPECS.items()},
            'noteExpression':{'presets':['rigid','default'],'expValueX':[0,1],'expValueY':[0,1],'vibratoModulation':[0,2]},
            'pitchFlatten':{'transitionMs':[0,500],'scoreTimingChanged':False,'existingEdits':'explicit replacement on entire groups only'},
            'articulation':{'gapMs':[.01,1000],'scoreChange':True},
            'effects':{'fields':SCHEMA,'bounds':'Supported CLI contract; not an exhaustive vendor limit table. Unspecified numeric bounds require finite values.','reverbTypes':['clean']},
            'timePositions':'integer blicks, or strings with b:/q:/s:/bar: prefixes',
            'unknownFields':'rejected', 'referenceSelectors':'reference UUIDs, distinct from group UUIDs'}
