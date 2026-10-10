// The loop trainer on the real api.js + mock.js (mock mode), with fake recording. Run: node --test frontend/tests/exercise_mock.test.mjs
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import { installFakeDom, settle, space } from './fake_dom.mjs';

const dom = installFakeDom();
dom.window.location.search = '?mock=1';
globalThis.fetch = async (url) => { // mock.js fetches mock/<file>.json relative to the page
  const body = await readFile(new URL(`../${url}`, import.meta.url), 'utf8');
  return { ok: true, status: 200, json: async () => JSON.parse(body) };
};
const api = await import('../js/api.js');
const { createTrainer } = await import('../js/exercise/trainer.js');

async function open(ex) {
  const root = dom.document.createElement('main');
  dom.body.append(root);
  const recorded = [];
  const trainer = createTrainer(root, {
    sessionId: 'sess_mock1', ex, beatsPerBar: 4, countInBeats: 4, metronomeOn: false,
    thresholds: { intervalMs: 10, slowAfterMs: 1e6, giveUpAfterMs: 1e6 }, onFullTake() {},
  }, {
    ...api,
    openStream: async () => ({ stream: {}, hasVideo: false, cameraError: null }),
    recordTake: async (options) => {
      recorded.push(options);
      return { stop: async () => ({ file: new File(['x'], 'rec.webm'), downbeat_s: 4.5, message: null }) };
    },
    stopStream() {},
  });
  await trainer.start();
  const waitFor = async (check) => { for (let i = 0; i < 40 && !check(); i += 1) await settle(); };
  const playRep = async (done) => {
    dom.document.dispatch('keydown', space());
    await waitFor(() => root.texts('stage').some((s) => s.startsWith('Recording')));
    dom.document.dispatch('keydown', space());
    await waitFor(done);
  };
  return { root, trainer, recorded, playRep };
}

test('mock exercise ex1: card, a passing rep fills the dots from the mock result', async () => {
  const t = await open('ex1');
  assert.ok(t.root.texts('pass-mark')[0].includes('average timing within 60 ms'));
  assert.equal(t.root.withClass('dot').length, 3);
  assert.equal(t.root.texts('current-tempo')[0], 'Current tempo: 66 BPM');
  await t.playRep(() => t.root.withClass('verdict').length > 0);
  assert.equal(t.root.texts('verdict')[0], 'PASS');
  assert.equal(t.root.withClass('filled').length, 2); // get_rep.json: streak 2
  assert.equal(t.recorded[0].tempoBpm, 66);
  t.trainer.destroy();
});

test('mock exercise ex_fail: FAIL with the reasons', async () => {
  const t = await open('ex_fail');
  await t.playRep(() => t.root.withClass('verdict').length > 0);
  assert.equal(t.root.texts('verdict')[0], 'FAIL');
  assert.deepEqual(t.root.withClass('reasons')[0].children.map((li) => li.textContent), ['2 errors, pass mark 0', 'mean timing 72 ms, pass mark 60 ms']);
  t.trainer.destroy();
});

test('mock exercise ex_not_counted: the back end message and Record again', async () => {
  const t = await open('ex_not_counted');
  await t.playRep(() => t.root.button('Record again'));
  assert.ok(t.root.texts('reasons')[0].includes('No notes were heard'));
  t.trainer.destroy();
});

test('mock exercise ex_complete: the rep passes the target and Done appears; ex_done opens on Done', async () => {
  const t = await open('ex_complete');
  assert.equal(t.root.texts('current-tempo')[0], 'Current tempo: 96 BPM');
  await t.playRep(() => t.root.button('Record a full take'));
  assert.deepEqual(t.root.texts('verdict'), ['PASS', 'Done']);
  t.trainer.destroy();
  const done = await open('ex_done');
  assert.deepEqual(done.root.texts('verdict'), ['Done']);
  done.trainer.destroy();
});
