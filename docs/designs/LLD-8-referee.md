# LLD-8 Score referee agent (r1)

Design text as given by ARCHITECT-10 (brief M-320). Changes 1 and 2 are built here (bar checks, referee agent, tools, checker, apply). Hooking into scan_job.py and the routes is change 3.

## Data
- `RefereeResult.referee = { status: 'done'|'skipped'|'failed', reason: str|null, rulings: [Ruling], model_id: str|null, elapsed_ms: int }`. `Ruling = { bar, pick: 'homr'|'reader'|'neither', why: str, confidence 0-1, accepted: bool, rejected_because: str|null }`.
- `DoubtfulBar` gains `referee_note: str|null` (the referee's why when its ruling was not accepted or it picked 'neither'). Accepted bars leave `doubtful_bars`. `double_checked` unchanged.
- `BarCheck` per reading of a bar: `{ length_ok (lengths sum to the time signature; the first bar may be a pickup), range_ok (every pitch within trumpet written range F#3..D6), key_ok (no accidental contradicting the key signature without a natural or earlier accidental in the bar), beats, expected_beats }`.

## Contracts
- `referee.run(score: Score, reading: Reading, compare: CompareResult, image_path: Path) -> RefereeResult { score (accepted bars replaced), compare (doubtful_bars shrunk and annotated), referee dict }`. Never raises; on failure returns inputs unchanged with status 'failed'.
- Strands `@tool` functions (plain code, read-only except `submit_ruling`): `list_doubtful_bars() -> [{bar, homr_text, reader_text}]`; `get_bar(bar) -> {bar, homr: {text, checks}, reader: {text, checks}|null, time_signature, key_signature}`; `look_at_bar(bar)` -> the photo cropped to that bar, or the whole photo if bar positions are unknown, as an image content block; `submit_ruling(bar, pick, why, confidence) -> {accepted, rejected_because}`. Unknown bar -> `{error: 'unknown_bar'}`. Tools are bound to one run's state (a class instance or closures), not module globals.
- Limits: at most 20 doubtful bars refereed (rest stay doubtful), 60 s overall. Constants (0.7 floor, 20, 60 s, range) live in a config.

## Logic
1. Trigger: doubtful_bars empty -> 'skipped' 'nothing_to_check'; AI off (AI_ENABLED false or ConfigError from settings) -> 'skipped' 'ai_off'; mostly-different warning from compare -> 'skipped' 'mostly_different'. Nothing else changes.
2. Code checks: BarCheck for homr's and reader's version of each doubtful bar; time and key signature from the homr score.
3. Referee: Strands Agent with the Bedrock vision model (settings.vision_model) and the 4 tools. System prompt: you are a referee between two readings of a photo of trumpet music; for each doubtful bar call get_bar, call look_at_bar when the checks don't settle it, then call submit_ruling once; prefer a reading whose checks all pass; pick 'neither' when unsure; never invent notes. Daemon thread, 60 s overall timeout, cancel signal. The agent factory is injectable so tests replace it with a stub that calls the tools in a fixed order.
4. Checker inside submit_ruling: accepted only if bar is doubtful and not yet ruled, pick is homr or reader, the picked reading exists, its length_ok and range_ok are true, and confidence >= 0.7. Else rejected_because is one of 'unknown_bar', 'already_ruled', 'neither', 'no_reading', 'length', 'range', 'low_confidence'. key_ok false is shown but doesn't reject.
5. Apply: accepted 'reader' -> replace that bar's notes in the Score with the reader's notes (pitch from name, length from length word, via note_text's mapping); accepted 'homr' -> no change. Remove accepted bars from doubtful_bars; set referee_note = why on the remaining ruled bars. Unruled bars stay with referee_note null. If converting a reader bar fails: that ruling accepted false, rejected_because 'apply_failed', bar stays doubtful.
6. Trace: each tool call and ruling is appended to the agent trace (trace.py) under agent 'referee'.

## Errors
Bedrock error / timeout -> log, status 'failed', reason 'model_error' or 'timeout'; rulings accepted before the failure are still applied. look_at_bar crop failure -> whole photo; if that fails -> `{error:'no_image'}`.

## Build notes (changes 1 and 2)
- `Score` had no key signature, so it gains `key_fifths: int | None` (sharps positive, flats negative; None = unknown, key_ok is then true), filled by parse.py from music21 and read back with a default so old score.json files still load.
- Trace has no session id (it is an in-memory object per run), so `run` takes an optional `trace: Trace`.
- homr is consumed only as MusicXML (homr_runner.py), so no bar positions reach the referee; `run` takes optional `bar_boxes` {bar: (left, top, right, bottom)} and crops when given, else sends the whole photo.
- compare_bars returns no doubtful bars when the readings mostly differ, so the skip checks run in the order mostly_different, nothing_to_check, ai_off.
- Extra checker rejection `run_over` (a ruling arriving after the run timed out). An accepted reader pick for a bar the Score does not have becomes `apply_failed`.
- The daemon-thread helper repeats reader_agent._run_with_timeout in shape; merging them would touch the reader, so it was left out of scope.
