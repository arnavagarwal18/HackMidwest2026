// Node tests for hash routing (js/router.js). Run: node --test frontend/tests/router.test.mjs
import assert from 'node:assert/strict';
import test from 'node:test';
import { installFakeBrowser } from './fake_env.mjs';

installFakeBrowser();
const { matchRoute } = await import('../js/router.js');

// Runs fn with console.error captured, returning the logged messages.
function captureErrors(fn) {
  const original = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args.map(String).join(' '));
  try {
    fn();
  } finally {
    console.error = original;
  }
  return logged;
}

test('a normal encoded hash still decodes its params', () => {
  assert.deepEqual(matchRoute('#/exercise/long%20tones%2F1'), { screen: 'exercise', params: { ex: 'long tones/1' } });
  assert.deepEqual(matchRoute('#/results/take_1'), { screen: 'results', params: { take: 'take_1' } });
});

test('a malformed encoded param does not throw: it is logged and routes to the not-found fallback', () => {
  for (const hash of ['#/results/%E0%A4%A', '#/exercise/%', '#/trace/%zz']) {
    let match;
    const logged = captureErrors(() => {
      match = matchRoute(hash);
    });
    assert.equal(match, null, hash);
    assert.equal(logged.length, 1, hash);
    assert.ok(logged[0].includes(hash), `the log names the bad hash ${hash}`);
  }
});

test('unknown or malformed paths with no params are not found and do not throw', () => {
  for (const hash of ['#/%', '#/take/%E0%A4%A', '']) {
    assert.equal(matchRoute(hash), null, hash);
  }
});
