"""Read-only comparison of an SVP against an independently reviewed lyric plan.

No synthesis, phoneme inference, original-score verification or listening claims.
Times in the plan are absolute quarter-note beats; SVP values are integer blicks.
"""
from fractions import Fraction

QUARTER = 705600000


def schema():
    return {'units':'absolute quarter-note beats (numbers or fraction strings)',
            'required':{'source':['reference','reviewed'],'track':['selector','phrases'],
                        'phrase':['id','start','end','text','notes'],
                        'note':['at','dur','pitch','lyrics']},
            'optional':{'note':['phonemes']},'unknownFields':'rejected',
            'textOnly':'notes may be omitted only for diagnosis with --text-only',
            'renderGate':'--lyrics-plan requires a declared-reviewed plan matching every audible project note before plugin loading',
            'boundary':'The caller must independently establish the source mapping; this command does not read or validate the source score.',
            'example':{'source':{'reference':'Replace with source edition/page/bar and actual review evidence','reviewed':False},
                       'tracks':[{'selector':'#1','phrases':[{'id':'verse-1-line-1','start':'0','end':'4','text':'山河','notes':[
                           {'at':'0','dur':'1','pitch':60,'lyrics':'山'},
                           {'at':'1','dur':'1','pitch':62,'lyrics':'-'},
                           {'at':'2','dur':'2','pitch':64,'lyrics':'河'}]}]}]}}


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(label + ' must be an integer')
    return value


def blick(value):
    if isinstance(value, bool):
        raise ValueError('Beat position cannot be boolean')
    result = Fraction(str(value)) * QUARTER
    if result.denominator != 1:
        raise ValueError('Beat position is not representable as integer blicks: ' + str(value))
    return int(result)


def keys(obj, allowed, required):
    if not isinstance(obj, dict):
        raise ValueError('Expected an object')
    if set(obj) - set(allowed) or set(required) - set(obj):
        raise ValueError('Invalid keys: unknown=%s missing=%s' %
                         (sorted(set(obj)-set(allowed)), sorted(set(required)-set(obj))))


def string(value, label):
    if not isinstance(value, str):
        raise ValueError(label + ' must be text')
    return value


def flatten(project):
    library = {g['uuid']: g for g in project.get('library', [])}
    tracks = []
    ignored = 0
    for ti, track in enumerate(project['tracks']):
        refs = []
        if 'mainRef' in track and 'mainGroup' in track:
            refs.append((track['mainRef'], track['mainGroup']))
        refs.extend((r, library[r['groupID']]) for r in track.get('groups', []))
        notes = []
        for ri, (ref, group) in enumerate(refs):
            offset = integer(ref.get('blickOffset', 0), 'blickOffset')
            pitch_offset = integer(ref.get('pitchOffset', 0), 'pitchOffset')
            for ni, n in enumerate(group.get('notes', [])):
                if (ref.get('isInstrumental') or ref.get('mute') or track.get('mixer', {}).get('mute')
                        or not track.get('renderEnabled', True) or n.get('attributes', {}).get('muted')):
                    ignored += 1
                    continue
                notes.append({'at': offset + integer(n['onset'], 'onset'),
                              'dur': integer(n['duration'], 'duration'),
                              'pitch': pitch_offset + integer(n['pitch'], 'pitch'),
                              'lyrics': string(n.get('lyrics', ''), 'lyrics'),
                              'phonemes': string(n.get('phonemes', ''), 'phonemes'),
                              'location': [ti+1, ri, ni]})
        notes.sort(key=lambda n: n['at'])
        tracks.append({'name': track.get('name', ''), 'notes': notes})
    return tracks, ignored


def text(notes):
    return ''.join(n['lyrics'] for n in notes if n['lyrics'] != '-')


def audit(project, plan, text_only=False, require_full=False):
    keys(plan, ['source', 'tracks'], ['source', 'tracks'])
    keys(plan['source'], ['reference', 'reviewed'], ['reference', 'reviewed'])
    if not string(plan['source']['reference'], 'source reference').strip():
        raise ValueError('source reference is empty')
    if not isinstance(plan['source']['reviewed'], bool):
        raise ValueError('source.reviewed must be boolean')
    if not isinstance(plan['tracks'], list) or not plan['tracks']:
        raise ValueError('Plan must select at least one track')
    tracks, ignored = flatten(project)
    errors, warnings, results = [], [], []
    selected, covered, mapped = set(), set(), set()
    for target in plan['tracks']:
        keys(target, ['selector', 'phrases'], ['selector', 'phrases'])
        selector = string(target['selector'], 'selector')
        if selector.startswith('#'):
            ti = int(selector[1:])-1
            if not 0 <= ti < len(tracks):
                raise ValueError('Track index outside project: ' + selector)
        else:
            matches = [i for i, t in enumerate(tracks) if t['name'] == selector]
            if len(matches) != 1:
                raise ValueError('Track name must match exactly once: ' + selector)
            ti = matches[0]
        if ti in selected:
            raise ValueError('Track selected more than once: ' + selector)
        selected.add(ti)
        if not isinstance(target['phrases'], list) or not target['phrases']:
            raise ValueError('Selected track must contain phrases')
        intervals, ids = [], set()
        all_notes = tracks[ti]['notes']
        for phrase in target['phrases']:
            keys(phrase, ['id', 'start', 'end', 'text', 'notes'], ['id', 'start', 'end', 'text'])
            identity = string(phrase['id'], 'phrase id')
            if not identity or identity in ids:
                raise ValueError('Phrase ids must be nonempty and unique per track')
            ids.add(identity)
            start, end = blick(phrase['start']), blick(phrase['end'])
            if start < 0 or start >= end or any(start < b and a < end for a, b in intervals):
                raise ValueError('Phrase intervals must be positive and non-overlapping')
            intervals.append((start, end))
            expected_text = string(phrase['text'], 'phrase text')
            notes = [n for n in all_notes if start <= n['at'] < end]
            location = {'track': '#'+str(ti+1), 'trackName': tracks[ti]['name'], 'phrase': identity}
            count_before = len(errors)
            if any(n['at'] < start < n['at']+n['dur'] or n['at'] < end < n['at']+n['dur'] for n in all_notes):
                errors.append(dict(location, code='phrase_cuts_sustain'))
            if not notes:
                errors.append(dict(location, code='empty_phrase'))
            if text(notes) != expected_text:
                errors.append(dict(location, code='text_mismatch', expected=expected_text, actual=text(notes)))
            for n in notes:
                covered.add(tuple(n['location']))
                if not n['lyrics'].strip():
                    errors.append(dict(location, code='empty_lyric', note=n['location']))
                if n['lyrics'] == '-':
                    prior = [q for q in all_notes if q['at'] < n['at']]
                    if not any(q['lyrics'].strip() and q['lyrics'] != '-' for q in prior):
                        errors.append(dict(location, code='orphan_continuation', note=n['location']))
                    elif prior and prior[-1]['at']+prior[-1]['dur'] < n['at']:
                        warnings.append(dict(location, code='continuation_across_gap_requires_score_review', note=n['location']))
            expected = phrase.get('notes')
            if expected is None:
                if not text_only:
                    errors.append(dict(location, code='missing_note_map'))
            else:
                if not isinstance(expected, list) or not expected:
                    raise ValueError('notes must be a nonempty list')
                normalized = []
                for n in expected:
                    keys(n, ['at', 'dur', 'pitch', 'lyrics', 'phonemes'], ['at', 'dur', 'pitch', 'lyrics'])
                    row = {'at': blick(n['at']), 'dur': blick(n['dur']),
                           'pitch': integer(n['pitch'], 'pitch'), 'lyrics': string(n['lyrics'], 'lyrics')}
                    if row['dur'] <= 0 or row['at'] < start or row['at']+row['dur'] > end or not 0 <= row['pitch'] <= 127:
                        raise ValueError('Expected note outside phrase or invalid duration/pitch')
                    if 'phonemes' in n:
                        row['phonemes'] = string(n['phonemes'], 'phonemes')
                    normalized.append(row)
                if [n['at'] for n in normalized] != sorted(n['at'] for n in normalized):
                    raise ValueError('Expected notes must be ordered by onset')
                if text(normalized) != expected_text:
                    raise ValueError('Plan text and its own note map disagree: ' + identity)
                if len(notes) != len(normalized):
                    errors.append(dict(location, code='note_count_mismatch', expected=len(normalized), actual=len(notes)))
                for index, (want, got) in enumerate(zip(normalized, notes)):
                    difference = {k: {'expected': v, 'actual': got[k]} for k, v in want.items() if v != got[k]}
                    if difference:
                        errors.append(dict(location, code='note_mapping_mismatch', index=index, differences=difference))
                if len(errors) == count_before:
                    mapped.update(tuple(n['location']) for n in notes)
            results.append(dict(location, expectedText=expected_text, actualText=text(notes),
                                noteCount=len(notes), noteMapProvided=expected is not None,
                                matches=len(errors) == count_before))
    total = sum(len(t['notes']) for t in tracks)
    if require_full and (not total or len(mapped) != total):
        errors.append({'code': 'unmapped_project_notes', 'count': total-len(mapped)})
    return {'planMatches': not errors, 'sourceReference': plan['source']['reference'],
            'sourceReviewDeclared': plan['source']['reviewed'],
            'originalScoreIndependentlyVerified': False, 'computedPhonemesVerified': False,
            'subjectiveListeningVerified': False, 'textOnlyMode': text_only,
            'projectAudibleNotes': total, 'ignoredMutedOrInstrumentalNotes': ignored,
            'scopedNotes': len(covered), 'exactlyMappedNotes': len(mapped),
            'allProjectNotesMapped': bool(total) and len(mapped) == total,
            'phrases': results, 'errors': errors, 'warnings': warnings,
            'boundary': 'Matches the supplied plan only; no proof of source-score correctness, computed pronunciation or rendered singing.'}

