# LLD-5 change 2: Measurement tools and Checker

Plain Python, no model, no `strands-agents` yet. Code lives in `backend/app/agents/`:

| File | Responsibility |
|---|---|
| `context.py` | `CheckContext`: one take's data through injected callables; id kinds; clean tempo |
| `claims.py` | Rules (a) to (c) for one claim and for the text that states it |
| `checker.py` | `check_feedback`, `check_plan`; sentence rules (a) to (e) |
| `plan_rules.py` | Plan rules for each exercise |
| `report.py` | `Report`: the shared `{ ok, problems, claims_checked, claims_failed }` result |
| `tools.py` | `make_tools(...)`: six read-only measurement tools |

## Data (from LLD-3 and LLD-4)

`take.diagnosis = { transposition, latency_ms, grid, played_bpm, target_bpm, alignment_quality, cant_tell, cant_tell_reason, error_rate, notes, extras, bars, problems, tier1 }`

- NoteResult `{ id 'n:{take}:{bar}:{idx}', bar, idx, expected_name, expected_midi, expected_onset_s, status 'ok'|'wrong'|'missed'|'uncertain', played_i, played_name, played_midi_float, cents_off, timing_ms (positive late), confidence }`
- Extra `{ id 'x:{take}:{i}', played_i, bar, onset_s, played_name, confidence }`
- BarResult `{ id 'b:{take}:{bar}', bar, expected, ok, wrong, missed, extra, uncertain, mean_timing_ms, local_bpm, drift_pct (positive faster), drift 'rushing'|'dragging'|'steady'|null }`
- Problem `{ id 'p:{take}:{k}', kind 'notes'|'late'|'early'|'rushing'|'dragging'|'form', bars, first_time_s, measurement_ids, size, certainty, score, tier 1|2|3, numbers }` where numbers is e.g. `{wrong:2, missed:1}` or `{mean_ms:90, count:4}`
- Form flag `{ id 'f:{take}:{k}', rule, label, direction, start_s, end_s, peak_s, bars, severity, confidence }` (shape from LLD-4)

Form data is not in `take.diagnosis`. The tools and Checker read it through `get_form` as
`{ status, tracking_quality, instrument, flags, rules_skipped }`. Earlier takes on the same bars come from
`get_earlier_takes` as `[{ take_id, error_rate, played_bpm }]`. **Assumed shapes:** the `get_form` dict, and
`tier1` items; confirm them when the diagnosis and form modules merge.

## Output shapes

- **Claim** `{ type 'count'|'timing_ms'|'direction'|'tempo_pct'|'pitch'|'form'|'bar', id, field, value, time_s }`. `field` is `'wrong'|'missed'|'extra'|'late'|'early'` for counts, else null. `time_s` is set for form claims, else null.
- **CoachSentence** `{ text (<= 30 words), cites (>= 1 ids), claims, jump: { bar|null, time_s|null } }`
- **CoachOutput** `{ sentences (1 to 6), problem_ids (1 to 3) }`
- **Exercise** `{ id, title, text (<= 40 words), bar_from, bar_to, start_bpm, target_bpm, step_bpm, reps_to_pass, pass_mark { max_errors, max_mean_timing_ms|null, form_rule|null }, problem_ids, claims }`
- **PlannerOutput** `{ exercises (2 to 4) }`

## Checker API

```python
check_feedback(output, ctx) -> { ok, problems: [ { index, claim, reason } ], claims_checked, claims_failed }
check_plan(output, ctx)     -> same shape
```

`ctx` is a `CheckContext` from `build_context(session_id, take_id, get_diagnosis, lookup=None, get_form=..., get_earlier_takes=...)`.
`index` is the sentence or exercise number, or null for a whole-output problem. `claim` is null unless a claim failed.
`reason` starts with a stable key, then detail: `unknown id`, `uncited`, `count mismatch`, `timing mismatch`,
`direction mismatch`, `tempo mismatch`, `pitch mismatch`, `form mismatch`, `bar mismatch`, `stray number`,
`unclaimed direction`, `uncertain note`, `bad jump`, `bad claim`, `text too long`, plus plan keys below.
The Checker never raises; a malformed output or claim is a problem. A lookup that throws is logged and the id is
treated as unknown, so the output is rejected rather than trusted.

### Sentence rules

- **(a)** At least one cite, and every cited and claimed id exists (`lookup`); else `uncited` / `unknown id`.
- **(b)** Each claim is recomputed from the stored item:
  - count equals the stored count exactly (bar: `wrong|missed|extra`; problem: its `numbers`, and `late`/`early` from `numbers.count` for a problem of that kind);
  - `timing_ms` within 10 ms or 10% of the stored note timing, bar `mean_timing_ms` or problem `numbers.mean_ms` (either is enough);
  - direction matches a sign: late if timing > 0 (early if < 0), sharp if `cents_off` > 0 (flat if < 0), rushing if `drift_pct` > 0 (dragging if < 0), a problem of kind late/early/rushing/dragging, and for a form flag its `direction`. `fast` counts as `rushing`, `slow` as `dragging`;
  - `tempo_pct` within 1.5 points of `drift_pct` (the sign may be left to the direction claim, so the size alone is accepted);
  - `pitch` equals `played_name`;
  - `form`: `value` is the flag's rule and `time_s` lies in `start_s - 0.5` to `end_s + 0.5`;
  - `bar`: the item lies in that bar.
- **(c)** Text scan. Every number in the text (digits, with or without `ms`, `%`, `BPM`, or a time like `0:14`, which is read as seconds) must equal, after rounding to a whole number, a claim value or `time_s`, a cited bar number (the bar of any cited or claimed item, or a `bar` claim), or a jump bar or time. Digits inside a note name (`F#5`) are not numbers. Every direction word (late, early, sharp, flat, rushing, dragging, fast, slow, high, low) must have a direction claim with the same word (or its synonym).
- **(d)** No cited or claimed note may have status `uncertain`.
- **(e)** A jump with a bar needs that bar among the cited bars; a jump with a time needs that time inside a form flag of the take (with the 0.5 s margin). A jump with both null is allowed (no jump).
- Also: text at most 30 words; 1 to 6 sentences; 1 to 3 `problem_ids`, each an existing problem.

### Plan rules

2 to 4 exercises (`bad exercise count`). For each exercise:

- `bar_from <= bar_to`, both within the take's bar range (`bars outside range`); each `problem_ids` entry is an existing problem (`unknown id`) whose bars lie in the exercise's range.
- `30 <= start_bpm <= target_bpm`; `target_bpm` equals the take's target tempo for a whole-range exercise and is at most it otherwise (`bad tempo`).
- `start_bpm` at most the clean tempo + 2, or 70% of `target_bpm` + 2 when there is no clean tempo (`start too fast`).
- `step_bpm` 2 to 10 (`bad step`); `reps_to_pass` 1 to 5 (`bad reps`); `max_errors` 0 to 2; `form_rule`, if set, is a rule flagged in this take (`bad pass mark`).
- Text at most 40 words; its claims pass rules (a) and (b); its text passes (c), where the exercise's own bars, tempos, step, reps, pass-mark numbers and its problems' bars also count as allowed numbers.

**Clean tempo** (assumption, not in the brief): the fastest `played_bpm` among earlier takes on the same bars and this take whose `error_rate` is at most 0.05; none if there is none.

## Tools

`make_tools(session_id, take_id, *, get_diagnosis, lookup=None, get_form=..., get_earlier_takes=...)` returns a dict of
plain functions by name, each with type hints and a docstring so a later task can wrap them with Strands `@tool`.
Every callable is called with `(session_id, take_id)`; `lookup` also gets the id. Without `lookup`, ids resolve from the diagnosis and form flags.

Each tool is read-only and returns a JSON string of at most 8,000 characters. Lists are cut from the end (lists
are sorted by score, so the least important go first) and the result gains `"truncated": { list_name: items_dropped }`.
Bad input or missing data returns `{ "error": ... }`; unexpected failures are logged and returned the same way. Nothing raises.

| Tool | Returns |
|---|---|
| `get_take_overview()` | `{ cant_tell, cant_tell_reason, alignment_quality, played_bpm, target_bpm, clean_bpm, counts (ok, wrong, missed, uncertain, extra), tier1, form_status, tracking_quality, instrument, bar_from, bar_to }` |
| `list_problems(max_tier=2)` | `{ problems }` of tier <= `max_tier` (1 to 3), best score first |
| `get_bar(bar)` | `{ bar: BarResult, notes, form_flags }`, or `{ error: 'bar out of range a-b' }` |
| `get_measurement(id)` | `{ item }`, or `{ error: 'unknown id' }` |
| `list_form_flags()` | `{ flags, rules_skipped }`, worst severity first |
| `get_history()` | `{ takes: [{ take_id, error_rate, played_bpm }], clean_bpm }` |

## Tests

`backend/tests/test_checker_feedback.py`, `test_checker_plan.py`, `test_tools.py`, using the hand-written
`backend/tests/fixtures/diagnosis_fixture.json` (one 4-bar take with wrong, missed, extra, uncertain and late notes, one form flag and two earlier takes).
