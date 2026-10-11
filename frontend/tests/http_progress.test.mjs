// Node tests for upload progress through the HTTP layer (js/xhr.js behind js/http.js), with a fake XMLHttpRequest.
// Run: node --test frontend/tests/http_progress.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeBrowser } from './fake_env.mjs';

installFakeBrowser({ search: '' }).restore(); // not mock mode: requests go through the XMLHttpRequest below
const { uploadTake, ApiError } = await import('../js/api.js');
const { postForm } = await import('../js/http.js');

// Each request announces itself; the test drives it with progress(), answer() or fail().
const sent = [];
globalThis.XMLHttpRequest = class {
  constructor() {
    this.listeners = {};
    this.upload = { addEventListener: (type, fn) => { this.listeners[`upload.${type}`] = fn; } };
    sent.push(this);
  }

  open(method, url) { this.method = method; this.url = url; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  send(body) { this.body = body; }
  progress(loaded, total, lengthComputable = true) { this.listeners['upload.progress']({ loaded, total, lengthComputable }); }
  answer(status, text) { Object.assign(this, { status, responseText: text }); this.listeners.load(); }
};

const VIDEO = new File(['mp4'], 'playing.mp4', { type: 'video/mp4' });
const FIELDS = { kind: 'video', source: 'uploaded' };

test('an upload with a progress callback goes through XMLHttpRequest with the File itself and reports the bytes sent', async () => {
  const seen = [];
  const pending = uploadTake('sess_1', VIDEO, FIELDS, (progress) => seen.push(progress));
  const [request] = sent.splice(0);
  assert.equal(request.method, 'POST');
  assert.equal(request.url, '/sessions/sess_1/takes');
  assert.equal(request.body.get('file'), VIDEO);
  assert.equal(request.body.get('kind'), 'video');
  request.progress(1000, 4000);
  request.progress(0, 0, false); // an unknown total is ignored
  request.progress(4000, 4000);
  request.answer(200, '{"take_id":"take_9","status":"processing"}');
  assert.deepEqual(await pending, { take_id: 'take_9', status: 'processing' });
  assert.deepEqual(seen, [{ loaded: 1000, total: 4000 }, { loaded: 4000, total: 4000 }]);
});

test('a server error answer becomes an ApiError with the server\'s message', async () => {
  const pending = uploadTake('sess_1', VIDEO, FIELDS, () => {});
  sent.splice(0)[0].answer(413, '{"error":{"code":"file_too_large","message":"That recording is too big."}}');
  await assert.rejects(pending, (err) => err instanceof ApiError && err.code === 'file_too_large' && err.message === 'That recording is too big.' && err.status === 413);
});

test('a non-JSON answer is reported as an unexpected response and logged', async () => {
  const original = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args.map(String).join(' '));
  try {
    const pending = postForm('/sessions/sess_1/takes', { file: VIDEO }, {}, () => {});
    sent.splice(0)[0].answer(502, '<html>bad gateway</html>');
    await assert.rejects(pending, (err) => err.code === 'http_502');
  } finally {
    console.error = original;
  }
  assert.ok(logged.some((line) => line.includes('non-JSON body (HTTP 502)')));
});
