// Node tests for the trace and progress empty states, the trace labels and mock, and the mic-blocked console output.
// Run: node --test frontend/tests/lld7_fixes.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { FakeNode, installFakeBrowser } from './fake_env.mjs';

const env = installFakeBrowser({ search: '' }); // not mock mode, so tests below can stub fetch
env.restore();

const { state } = await import('../js/state.js');
const { render: renderTraceScreen, renderTrace, NO_TRACE_TEXT } = await import('../js/screens/trace.js');
const { render: renderProgressScreen, renderProgress, NO_PROGRESS_TEXT } = await import('../js/screens/progress.js');
const { toMediaAccessError } = await import('../js/media_error.js');

const NOT_FOUND = { error: { code: 'trace_missing', message: 'No trace.' } };
const stubFetch = (status, body) => { globalThis.fetch = async () => ({ ok: status < 400, status, json: async () => body }); };
const mockTrace = JSON.parse(readFileSync(new URL('../mock/get_trace.json', import.meta.url), 'utf8'));
const quietly = (body) => async () => { // keeps the expected console output out of the test report
  const real = { warn: console.warn, error: console.error };
  console.warn = () => {};
  console.error = () => {};
  try { await body(); } finally { Object.assign(console, real); }
};

state.session_id = 'sess_1';

test('a 404 trace shows the empty state, not an error', quietly(async () => {
  stubFetch(404, NOT_FOUND);
  const root = new FakeNode('main');
  await renderTraceScreen(root, { fb: 'fb_9' });
  assert.ok(root.hasText(NO_TRACE_TEXT));
  assert.equal(NO_TRACE_TEXT, 'No trace for this feedback yet.');
}));

test('other trace errors still reach the caller, which shows the banner', quietly(async () => {
  stubFetch(500, { error: { code: 'server_error', message: 'Boom.' } });
  await assert.rejects(renderTraceScreen(new FakeNode('main'), { fb: 'fb_9' }), (err) => err.status === 500);
}));

test('a 404 progress shows the empty state, other errors are rethrown', quietly(async () => {
  stubFetch(404, { error: { code: 'session_not_found', message: 'No session.' } });
  const root = new FakeNode('main');
  await renderProgressScreen(root);
  assert.ok(root.hasText('No progress yet: record a take first.'));
  assert.equal(NO_PROGRESS_TEXT, 'No progress yet: record a take first.');
  stubFetch(500, { error: { code: 'server_error', message: 'Boom.' } });
  await assert.rejects(renderProgressScreen(new FakeNode('main')), (err) => err.status === 500);
}));

test('the mock trace uses the event names the backend emits, and each has a friendly label', () => {
  const real = new Set(['model_start', 'model_end', 'model_error', 'tool_start', 'tool_end', 'tool_error', 'error', 'check_pass', 'check_fail', 'dropped', 'fallback']);
  assert.ok(mockTrace.events.every((event) => real.has(event.event)), 'only real event names');
  const root = new FakeNode('main');
  renderTrace(root, mockTrace);
  const markers = root.find((node) => node.className === 'trace-marker').map((node) => node.textContent);
  assert.equal(markers.length, mockTrace.events.length);
  assert.ok(!markers.some((marker) => marker.includes('_')), 'no raw event name is shown');
});

test('trace shows the instructor and referee by name and labels the error events', () => {
  const events = [
    { t_ms: 0, agent: 'instructor', event: 'model_error', name: 'model', detail: 'TimeoutError', duration_ms: 5 },
    { t_ms: 9, agent: 'referee', event: 'tool_error', name: 'rate', detail: 'ValueError', duration_ms: 1 },
    { t_ms: 12, agent: 'coach', event: 'error', name: 'RuntimeError', detail: '', duration_ms: 0 },
  ];
  const root = new FakeNode('main');
  renderTrace(root, { mode: 'ai', events });
  const headings = root.find((node) => node.tagName === 'h3').map((node) => node.textContent);
  assert.deepEqual(headings, ['Instructor', 'Referee', 'Coach']);
  const titles = root.find((node) => node.className === 'trace-title').map((node) => node.textContent);
  assert.deepEqual(titles, ['the model call failed', 'tool failed: rate', 'stopped with an error: RuntimeError']);
});

test('progress shows none yet for a missing error rate', () => {
  const snapshot = { source: 'take', bar_from: 1, bar_to: 2, errors: 0, error_rate: null, played_bpm: null, clean_bpm: null, form_flags: 0, form_checked: false };
  const makeElement = document.createElement;
  document.createElement = (tag) => { // the fake DOM has no table API
    const node = makeElement(tag);
    const section = () => Object.assign(new FakeNode('tbody'), { insertRow: () => { const row = new FakeNode('tr'); node.append(row); return row; } });
    return Object.assign(node, { createTHead: section, createTBody: section });
  };
  const root = new FakeNode('main');
  renderProgress(root, { before: snapshot, after: null, exercises: [] });
  document.createElement = makeElement;
  assert.ok(root.hasText('none yet') && !root.hasText('0%') && !root.hasText('NaN'));
});

test('a blocked mic is a warning in the console; only an unexpected failure is an error', () => {
  const calls = [];
  const real = { warn: console.warn, error: console.error };
  console.warn = (...args) => calls.push(['warn', ...args]);
  console.error = (...args) => calls.push(['error', ...args]);
  try {
    const blocked = toMediaAccessError('mic', Object.assign(new Error('denied'), { name: 'NotAllowedError' }));
    assert.equal(blocked.reason, 'blocked');
    assert.match(blocked.message, /not allowed to use the mic/);
    assert.deepEqual(calls.map(([level]) => level), ['warn']);
    toMediaAccessError('mic', new Error('odd'));
    assert.deepEqual(calls.map(([level]) => level), ['warn', 'error']);
  } finally {
    Object.assign(console, real);
  }
});
