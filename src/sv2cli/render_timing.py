"""First waveform-entry acceptance, independent of synthesis readiness."""
from pathlib import Path
from .errors import SVError
from .io import write_json
from .project import finite
from .timing import read_pcm
from .wave_align import entries, write as align_write


def accept(project, source, work, policy='check', tolerance=.03,landmark='broadband'):
    """Return a checked/explicitly aligned WAV and auditable timing evidence.

    Energy landmarks cannot establish phoneme or every-note timing. Mixed audio
    cannot establish any individual stem's entry and is never auto-aligned.
    """
    finite(tolerance, 'entry tolerance')
    if tolerance < .002 or policy not in {'check', 'align', 'report'}:
        raise SVError('Use check/align/report and an entry tolerance of at least 2 ms')
    source=Path(source);work=Path(work)
    mixes={i+1:t.get('mixer',{}) for i,t in project.tracks()}
    solos={i for i,m in mixes.items() if m.get('solo')}
    audible=sorted({n['track'] for n in project.notes() if not n['muted']
                    and not mixes[n['track']].get('mute')
                    and (not solos or n['track'] in solos)})
    report={'policy':policy,'toleranceSeconds':tolerance,'landmark':landmark,
            'method':'first-isolated-waveform-entry-2ms-'+landmark,
            'firstWaveformEntryVerified':False,'allNoteOnsetsVerified':False,
            'phonemeAlignmentVerified':False,'subjectiveListeningVerified':False,
            'scoreFingerprint':project.score_fingerprint(),'scoreUnchanged':True}
    def save():write_json(work/'entry-timing.json',report,force=True)
    if len(audible)!=1:
        report.update(status='unresolved',reason='isolated_stem_required')
        save()
        if policy!='report':
            raise SVError('Entry checking/alignment needs one audible stem. Use --stems, or --entry-policy report for an unchecked mix.', 'entry_timing_unresolved')
        return source,report
    selectors=[f'#{audible[0]}']
    audio,rate,_=read_pcm(source)
    measured=entries(project,audio,rate,selectors,landmark=landmark)
    if landmark!='broadband':report['broadbandEntriesBefore']=entries(project,audio,rate,selectors)
    report.update(entriesBefore=measured,entriesAfter=measured,
                  status='unresolved' if measured[0]['observed'] is None else 'measured')
    first=measured[0]
    if first['observed'] is not None:
        report['firstWaveformEntryVerified']=abs(first['delta'])<=tolerance
        report['status']='passed' if report['firstWaveformEntryVerified'] else 'outside_tolerance'
    save()
    if policy=='report':return source,report
    if first['observed'] is None:
        raise SVError('First waveform entry is unresolved; inspect entry-timing.json. No accepted output is written.', 'entry_timing_unresolved')
    if policy=='align':
        # Explicit opt-in: this moves the whole recording, preserving every
        # sample interval. Later phrase entries remain individually reported.
        target=work/'entry-aligned.wav'
        correction=align_write(project,source,target,selectors,tolerance=tolerance,landmark=landmark)
        report.update(status='aligned',firstWaveformEntryVerified=True,
                      entriesAfter=correction['allObservedEntriesAfter'],
                      advanceSeconds=correction['translations'][0]['advanceSeconds'],
                      alignmentReport=str(target.with_suffix('.alignment.json')))
        save()
        return target,report
    if not report['firstWaveformEntryVerified']:
        raise SVError(f"First waveform entry is {first['delta']:+.3f}s from the score (limit {tolerance:.3f}s). Inspect entry-timing.json; use --entry-policy align only for a reviewed whole-recording offset.", 'entry_timing_mismatch')
    return source,report
