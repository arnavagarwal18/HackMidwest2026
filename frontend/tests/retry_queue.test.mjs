// Requests that find the server down share one Retry and are cancelled on navigation. Run: node --test frontend/tests/retry_queue.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeDom, settle } from './fake_dom.mjs';

const dom = installFakeDom();
let serverUp = false;
globalThis.fetch = async (url) => {
  if (!serverUp) throw new TypeError('Failed to fetch');
  return { ok: true, status: 200, json: async () => ({ url }) };
};
const { get } = await import('../js/http.js');
const { RequestCancelled, isRequestCancelled } = await import('../js/request_cancelled.js');
const { reportError } = await import('../js/banner.js');

console.error = () => {}; // the transport logs each unreachable attempt; keep test output readable
const settled = (promise) => promise.then((value) => ({ value }), (error) => ({ error }));

test('two parallel failing requests both settle after one Retry', async () => {
  serverUp = false;
  const first = settled(get('/api/chat'));
  const second = settled(get('/api/results'));
  await settle();
  assert.equal(dom.banner.hidden, false);
  await dom.banner.button('Retry').click();
  assert.equal(dom.banner.hidden, false, 'still down: the banner stays and both keep waiting');
  serverUp = true;
  await dom.banner.button('Retry').click();
  assert.deepEqual(await first, { value: { url: '/api/chat' } });
  assert.deepEqual(await second, { value: { url: '/api/results' } });
  assert.equal(dom.banner.hidden, true);
});

test('leaving the screen rejects every queued request with the cancel error', async () => {
  serverUp = false;
  const first = settled(get('/api/chat'));
  const second = settled(get('/api/results'));
  await settle();
  dom.window.dispatch('hashchange');
  for (const outcome of [await first, await second]) assert.ok(isRequestCancelled(outcome.error));
  assert.ok((await first).error instanceof RequestCancelled);
  assert.equal(dom.banner.hidden, true, 'the Retry banner goes away with the requests it belonged to');
});

test('a cancelled request is not shown as a red error on the next screen', () => {
  dom.banner.hidden = true;
  dom.banner.textContent = '';
  reportError(new RequestCancelled());
  assert.equal(dom.banner.hidden, true);
});

test('a request that fails with a server error after Retry rejects only that request', async () => {
  serverUp = false;
  const outcome = settled(get('/api/broken'));
  await settle();
  globalThis.fetch = async () => ({ ok: false, status: 500, json: async () => ({ error: { code: 'boom', message: 'The server broke.' } }) });
  await dom.banner.button('Retry').click();
  assert.equal((await outcome).error.message, 'The server broke.');
});
