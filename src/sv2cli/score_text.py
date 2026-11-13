"""Full-score text export: section → bar → track → note with intervals."""
from .timing import musical

INTERVAL_NAMES = {
    0: 'P1', 1: 'm2', 2: 'M2', 3: 'm3', 4: 'M3', 5: 'P4',
    6: 'TT', 7: 'P5', 8: 'm6', 9: 'M6', 10: 'm7', 11: 'M7',
}
DISSONANT = {1, 2, 6, 10, 11}  # m2 M2 TT m7 M7

def _interval(semitones):
    s = abs(semitones)
    name = 'P8' if s and s % 12 == 0 else INTERVAL_NAMES[s % 12]
    octaves = s // 12
    direction = 'up' if semitones > 0 else 'dn' if semitones < 0 else 'uni'
    dissonant = (s % 12) in DISSONANT
    return {'semitones': semitones, 'name': name, 'octaves': octaves,
            'direction': direction, 'dissonant': dissonant}

def export(project):
    """
    Returns a dict structured as:
      { tracks: [ { track, name, sections: [ { label, bars: [
          { bar, notes: [ { beat, onset_q, duration_q, pitch, midi, lyrics,
                            phonemes, musicalType, interval_from_prev } ] }
        ] } ] } ] }
    """
    from .project import QUARTER
    from fractions import Fraction

    rows = project.notes()
    if not rows:
        return {'tracks': []}

    def blick_to_qbeats(b):
        return float(Fraction(b, QUARTER))

    # Attach bar/beat to every note
    enriched = []
    for r in rows:
        m = musical(project, r['onset'])
        enriched.append({**r,
                         'bar': m['bar'],
                         'beat': round(m['beat'], 4),
                         'onset_q': round(blick_to_qbeats(r['onset']), 4),
                         'duration_q': round(blick_to_qbeats(r['duration']), 4)})

    # Group by track
    track_map = {}
    for r in enriched:
        track_map.setdefault(r['track'], []).append(r)

    result_tracks = []
    for ti in sorted(track_map):
        notes = sorted(track_map[ti], key=lambda n: n['onset'])
        track_name = notes[0]['trackName']

        # Annotate intervals within each track
        prev_pitch = None
        for n in notes:
            if prev_pitch is not None:
                n['interval_from_prev'] = _interval(n['pitch'] - prev_pitch)
            else:
                n['interval_from_prev'] = None
            prev_pitch = n['pitch']

        # Group into bars
        bar_map = {}
        for n in notes:
            bar_map.setdefault(n['bar'], []).append(n)

        # Minimal section detection: label consecutive runs of bars
        # Caller can override with their own section map; this provides a default.
        bars_sorted = sorted(bar_map)
        sections = []
        sec_start = bars_sorted[0] if bars_sorted else 1
        prev_bar = sec_start
        for b in bars_sorted[1:]:
            if b > prev_bar + 1:  # gap → new section
                sections.append((sec_start, prev_bar))
                sec_start = b
            prev_bar = b
        if bars_sorted:
            sections.append((sec_start, bars_sorted[-1]))

        sec_dicts = []
        for (s_from, s_to) in sections:
            label = f'bars {s_from}–{s_to}'
            bar_dicts = []
            for b in range(s_from, s_to + 1):
                bar_notes = bar_map.get(b, [])
                note_dicts = []
                for n in bar_notes:
                    note_dicts.append({
                        'beat': n['beat'],
                        'onset_q': n['onset_q'],
                        'duration_q': n['duration_q'],
                        'pitch': n['pitch'],
                        'midi': n['pitch'],
                        'lyrics': n['lyrics'],
                        'phonemes': n['phonemes'],
                        'musicalType': n['musicalType'],
                        'interval_from_prev': n['interval_from_prev'],
                    })
                if note_dicts:
                    bar_dicts.append({'bar': b, 'notes': note_dicts})
            if bar_dicts:
                sec_dicts.append({'label': label, 'bars': bar_dicts})

        result_tracks.append({'track': ti, 'name': track_name, 'sections': sec_dicts})

    return {'tracks': result_tracks}
