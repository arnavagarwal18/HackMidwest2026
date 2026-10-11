// The new results states: scores and headline, detection chip text, can't-tell text, wait steps and Play again.
// Run: node --test frontend/tests/results_summary.test.mjs   (fake DOM, no browser)
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';

const { headline, percent, pitchScore, rhythmScore } = await import('../js/results/scores.js');
const { keyLabel } = await import('../js/results/transposition.js');
const { barRange, barsText, detectionText } = await import('../js/results/detection.js');
const { heardText, nextAction, NEXT_ACTIONS } = await import('../js/results/cant_tell.js');
const { currentStep, renderStepList, WAIT_STEPS } = await import('../js/results/wait_steps.js');
const { STAGES } = await import('../js/results/load.js');
const { renderStatStrip } = await import('../js/results/stats.js');
const { renderCantTell } = await import('../js/results/cant_tell.js');
const { renderWorking } = await import('../js/results/status.js');

const analysis = {
  bars: [{ bar: 1, expected: 4, ok: 4, wrong: 0, missed: 0, extra: 0, uncertain: 0 }, { bar: 2, expected: 4, ok: 2, wrong: 1, missed: 1, extra: 0, uncertain: 0 }],
  notes: [{ timing_ms: 10 }, { timing_ms: -85 }, { timing_ms: 80 }, { timing_ms: null }],
};

test('pitch is the share of notes right and rhythm the share within 80 ms, each null when nothing counts', () => {
  assert.deepEqual(pitchScore(analysis), { right: 6, expected: 8, share: 0.75 });
  assert.deepEqual(rhythmScore(analysis), { onTime: 2, timed: 3, share: 2 / 3 });
  assert.equal(pitchScore({ bars: [] }), null);
  assert.equal(rhythmScore({ notes: [{ timing_ms: null }] }), null);
  assert.equal(percent(0.755), '76%');
});

test('the headline names the weaker side, and drops rhythm when there is none', () => {
  const strong = { share: 0.9 };
  const weak = { share: 0.5 };
  assert.match(headline(strong, strong), /notes and the timing both held up/);
  assert.match(headline(strong, weak), /timing drifted/);
  assert.match(headline(weak, strong), /Steady timing, but some notes were off/);
  assert.match(headline(weak, weak), /rough one/);
  assert.match(headline(strong, null), /notes held up/);
  assert.equal(headline(null, null), null);
});

test('the summary has the headline, a pitch score and a rhythm score as separate tiles', () => {
  const summary = renderStatStrip(analysis);
  assert.match(summary.textContent, /Pitch.*6 of 8 notes right/);
  assert.match(summary.textContent, /Rhythm.*2 of 3 on the beat/);
  assert.ok(summary.children[0].className.includes('headline'));
  assert.equal(renderStatStrip({ bars: [] }), null);
});

test('the key label says the key and where it came from, in plain words', () => {
  assert.equal(keyLabel({ semitones: -4, source: 'detected' }), 'Key: -4, detected');
  assert.equal(keyLabel({ semitones: 3, source: 'user' }), 'Key: +3, set by you');
  assert.equal(keyLabel({ semitones: 2, source: 'file' }), 'Key: +2, from the score');
  assert.equal(keyLabel({ semitones: 0, source: 'default' }), 'Key: 0, instrument default');
  assert.equal(keyLabel({ semitones: -2, source: 'something_new' }), 'Key: -2', 'an unknown source is left out');
  assert.equal(keyLabel(null), 'Key: 0');
});

test('the detection chip says the key and the bars, and drops what is unknown', () => {
  assert.deepEqual(barRange({ bars: [{ bar: 3 }, { bar: 8 }] }), { from: 3, to: 8 });
  assert.deepEqual(barRange({ bars: [] }, { bar_from: 1, bar_to: 8 }), { from: 1, to: 8 });
  assert.equal(barRange({ bars: [] }, { bar_from: null, bar_to: null }), null);
  assert.equal(barsText({ from: 2, to: 2 }), 'bar 2');
  assert.equal(detectionText({ transposition: { semitones: -4, source: 'detected' }, bars: [{ bar: 1 }, { bar: 8 }] }), 'Key: -4, detected · bars 1–8');
  assert.equal(detectionText({ transposition: { semitones: 2, source: 'user' }, bars: [] }, {}), 'Key: +2, set by you');
});

test("can't tell says what was heard and picks one next action from the reason", () => {
  const heard = { notes: [{ played_i: 0 }, { played_i: null }, { played_i: 1 }], extras: [{}], alignment_quality: 0.21 };
  assert.equal(heardText(heard), 'What I heard: 3 notes heard, best match to the score 21%.');
  assert.equal(heardText({ notes: [], alignment_quality: 0.21 }), 'What I heard: best match to the score 21%.');
  assert.equal(heardText({ notes: [], alignment_quality: null }), null);
  assert.equal(nextAction({ cant_tell_reason: 'low_match' }), NEXT_ACTIONS.low_match);
  assert.match(nextAction({ cant_tell_reason: 'few_pairs' }), /closer to the microphone/);
  assert.match(nextAction({ cant_tell_reason: 'too_short' }), /longer range of bars/);
  assert.match(nextAction({ cant_tell_reason: null }), /closer to the microphone/);
});

test('the wait steps follow the stage: uploading done, the stage current, the rest pending', () => {
  assert.deepEqual(WAIT_STEPS, ['Uploading', 'Finding notes', 'Matching key and bars', 'Writing feedback']);
  assert.equal(currentStep(STAGES.processing), 1);
  assert.equal(currentStep(STAGES.feedback), 3);
  assert.equal(currentStep('something new'), 1);
  const states = renderStepList(STAGES.transcribed).children.map((item) => item.dataset?.state ?? item.attributes['data-state']);
  assert.deepEqual(states, ['done', 'done', 'current', 'pending']);
});

const primaryLabels = (view) => view.all().filter((n) => n.tagName === 'BUTTON' && n.className.split(' ').includes('primary')).map((n) => n.textContent);
const cantTellView = (reason) => {
  const view = dom.document.createElement('section');
  renderCantTell(view, { analysis: { cant_tell: true, cant_tell_reason: reason, alignment_quality: 0.2, notes: [] }, feedback: { sentences: [] }, plan: null }, { sessionId: 's', rerun() {}, note: null });
  return view;
};

test("can't tell has exactly one filled button: the key change for low_match, Record again otherwise", () => {
  assert.deepEqual(primaryLabels(cantTellView('low_match')), ['Change transposition']);
  assert.deepEqual(primaryLabels(cantTellView('few_pairs')), ['Record again']);
  assert.deepEqual(primaryLabels(cantTellView('too_short')), ['Record again']);
  assert.match(cantTellView('low_match').texts('stopped-message')[0], /couldn't tell/);
});

test('the wait screen has a Cancel button that goes back to recording', () => {
  const view = dom.document.createElement('section');
  renderWorking(view, STAGES.processing, false);
  assert.equal(view.texts('stage')[0], 'Hearing notes...');
  view.button('Cancel').click();
  assert.equal(dom.window.location.hash, '#/take');
});
