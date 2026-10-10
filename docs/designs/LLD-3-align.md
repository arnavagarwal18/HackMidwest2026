# LLD-3 change 1: Expected notes, alignment and marking (steps 1, 3, 4 of note diagnosis)

Code: `backend/app/diagnosis/{config,errors,expected,align,mark,take_alignment}.py`; tests in `backend/tests/test_diagnosis_align.py`. Pure Python on plain dicts. No routes or storage here. Entry point: `align_take(score, played, take, transposition_semitones) -> dict` in `take_alignment.py`.

## Input shapes

score.json: { title, instrument, tempo_bpm, time_signature:[int,int], written_transpose_semitones:int|null, bars:[ { bar:int (1-based), start_beat:float (quarter beats from start), beats:float, notes:[ { idx:int, pitch_midi:int|null (null=rest), name:str, start_beat:float (absolute), dur_beats:float, tied_from_previous:bool } ] } ], warnings:[str] }.

PlayedNote: { i:int, onset_s:float, offset_s:float, midi_float:float, midi:int, cents_off:float, confidence:float 0-1, voiced_ratio:float 0-1 }.

Take fields used: take_id ('t1'), bar_from, bar_to, tempo_bpm (target), downbeat_s (float|null), latency_s (calibration latency_ms/1000, 0 if none).

## Output shapes

NoteResult { id ('n:{take}:{bar}:{idx}'), bar, idx, expected_name, expected_midi (sounding), expected_onset_s, status 'ok'|'wrong'|'missed'|'uncertain', played_i|null, played_name|null, played_midi_float|null, cents_off|null, timing_ms|null (left null here; timing is a later task), confidence|null }.

Extra { id ('x:{take}:{i}'), played_i, bar, onset_s, played_name, confidence }.

`align_take` returns { notes: [NoteResult], extras: [Extra], grid: { kind 'metronome'|'fitted', offset_s, sec_per_beat }, fit: { offset_s, sec_per_beat } | null, alignment_quality, cant_tell, cant_tell_reason }.

## Step 1: expected notes

Take bars bar_from..bar_to; walk in order; skip rests; merge tied notes into one (length summed, onset of the first). Each gets id 'n:{take}:{bar}:{idx}', its onset in beats from the start of bar_from, and sounding pitch = written pitch_midi + transposition semitones (a parameter here).

## Step 3: line-up

Two passes of Needleman-Wunsch alignment over expected notes and played notes, both in time order. Scores: same midi +2; within 1 semitone -0.5; other substitution -1; gap (missed or extra) -1. Pass 1 has no time limit. From pass 1's pairs with the same midi, fit played onset_s = offset_s + beat x sec_per_beat by least squares (needs >= 3 pairs, else pass 1 stands). Pass 2 repeats the alignment allowing a pair only when the played onset is within +-1 beat of the fitted time. Grid: if downbeat_s is not null, kind 'metronome' with offset_s = downbeat_s - latency_s and sec_per_beat = 60 / target_bpm, else kind 'fitted' using the fit. expected_onset_s comes from the grid.

## Step 4: marking

For each aligned pair: ok if |midi_float - expected_midi| <= 0.5; otherwise uncertain if confidence < 0.5, else wrong. Expected note with no partner = missed. Played note with no partner = Extra if confidence >= 0.5, else dropped. cents_off = (midi_float - expected_midi) x 100 for pairs. alignment_quality = ok count / expected count. Can't tell when quality < 0.4 ('low_match'), or < 50% of expected notes have a partner ('few_pairs'), or < 3 expected notes ('too_short').

## Implementation choices where the design was silent

- Tie merge: a tied note merges into the directly preceding note only if that is a note of the same sounding pitch (a rest breaks a tie). A tied note with nothing to merge into (e.g. first note of the range) stands as its own expected note.
- expected_name: the score's name when transposition is 0, otherwise the sounding pitch spelled with sharps (e.g. 'D#4'). played_name is spelled the same way from `midi`.
- Played notes are sorted by onset_s before alignment; `played_i` keeps the original `i`.
- Needleman-Wunsch ties resolve to the earliest matches (the table scores from each position onward and the trace-back runs forward, preferring pairs).
- Fit is rejected (pass 1 stands) when the same-midi pairs all share one beat or the slope is not positive.
- Fitted grid with no usable fit (and no downbeat): sec_per_beat = 60 / target_bpm, offset_s = median of (played onset - beat x sec_per_beat) over pass-1 pairs, else the first played onset, else 0. `fit` is null in that case.
- Extra's bar: the bar containing its onset on the grid; before the range counts as the first bar, after it as the last.
- cant_tell checks run in the order too_short, low_match, few_pairs; "have a partner" counts every pair (ok, wrong, uncertain).
- Bad input (bar range not in the score, bar_from after bar_to, missing take/played fields, tempo_bpm <= 0) raises `DiagnosisInputError` with a readable message and is logged at warning level.
- cents_off is rounded to 2 decimals.

## Tests

Perfect take; bar 2 of a 4-bar scale with a wrong, a missed and an Extra; low-confidence mismatch is 'uncertain'; random notes and silence can't tell; 2-note range too_short; few_pairs; downbeat_s null with notes starting 2.3 s in at 90 BPM gives a fitted grid with sec_per_beat = 60/90; latency; pass 2 time window; tied-note merge; transposition; input errors.
