// Node tests for the DOM builders in js/ui/components.js (the CSS itself is checked by eye: see frontend/dev/screens/).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { installFakeDom } from './fake_dom.mjs';

installFakeDom();
const { badge, emptyState, pageHeader, skeleton, stat } = await import('../js/ui/components.js');

test('badge uses the tone class and rejects an unknown tone', () => {
  const node = badge('Complete', 'ok');
  assert.equal(node.className, 'badge badge-ok');
  assert.equal(node.textContent, 'Complete');
  assert.equal(badge('Draft').className, 'badge badge-neutral');
  assert.throws(() => badge('x', 'purple'), /Unknown badge tone "purple"/);
});

test('stat holds a value and a label, with an optional tone', () => {
  const node = stat(87, 'In tune', 'ok');
  assert.equal(node.className, 'stat stat-ok');
  assert.deepEqual(node.texts('stat-value'), ['87']);
  assert.deepEqual(node.texts('stat-label'), ['In tune']);
  assert.equal(stat('3', 'Takes').className, 'stat');
  assert.throws(() => stat(1, 'x', 'loud'), /Unknown stat tone/);
});

test('emptyState shows the title and, when given, the help line', () => {
  assert.deepEqual(emptyState('Nothing yet', 'Play a piece.').all().map((n) => n.textContent), ['Nothing yet', 'Play a piece.']);
  assert.equal(emptyState('Nothing yet').all().length, 1);
});

test('skeleton makes the asked number of lines', () => {
  assert.equal(skeleton(4).withClass('skeleton').length, 4);
});

test('pageHeader marks the current step and the done ones', () => {
  const node = pageHeader({ title: 'Play', subtitle: 'Pick a piece', steps: ['Choose', 'Play', 'Review'], currentStep: 1 });
  assert.deepEqual(node.texts('page-title'), ['Play']);
  assert.deepEqual(node.texts('page-subtitle'), ['Pick a piece']);
  const items = node.all().filter((n) => n.tagName === 'LI');
  assert.deepEqual(items.map((n) => n.className), ['is-done', '', '']);
  assert.deepEqual(items.map((n) => n.attributes['aria-current']), [undefined, 'step', undefined]);
});

test('pageHeader without steps has no step list, and a bad step fails loudly', () => {
  assert.equal(pageHeader({ title: 'Progress' }).withClass('steps').length, 0);
  assert.throws(() => pageHeader({ title: 'x', steps: ['a'], currentStep: 3 }), /outside the 1 steps/);
});

// ---------- Design tokens: contrast (WCAG 2.x) and tap targets, read from the stylesheets ----------
const appCss = readFileSync(new URL('../css/app.css', import.meta.url), 'utf8');
const componentsCss = readFileSync(new URL('../css/components.css', import.meta.url), 'utf8');

function tokensOf(block) {
  return Object.fromEntries([...block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})\b/g)].map((m) => [m[1], m[2]]));
}
const rootBlock = appCss.match(/:root \{([\s\S]*?)\n\}/)[1];
const darkBlock = appCss.match(/prefers-color-scheme: dark\) \{\s*:root \{([\s\S]*?)\n  \}/)[1];
const light = tokensOf(rootBlock);
const dark = { ...light, ...tokensOf(darkBlock) };

const channels = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const toHex = (rgb) => `#${rgb.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('')}`;
const mix = (hexA, percent, hexB) => toHex(channels(hexA).map((c, i) => (c * percent + channels(hexB)[i] * (100 - percent)) / 100)); // color-mix(in srgb, A p%, B)
const luminance = (hex) => {
  const [r, g, b] = channels(hex).map((c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };

for (const [mode, t] of [['light', light], ['dark', dark]]) {
  const surface2 = t['surface-2'];
  const soft = (name) => mix(t[name], 10, t.surface);
  const text = [
    ['ink on bg', t.ink, t.bg], ['ink on surface', t.ink, t.surface], ['muted on bg', t.muted, t.bg],
    ['muted on surface', t.muted, t.surface], ['ink on surface-2 (the unselected segment)', t.ink, surface2],
    ['ink on surface (the selected segment)', t.ink, t.surface], ['primary-ink on primary', t['primary-ink'], t.accent],
    ['primary-ink on primary-hover', t['primary-ink'], t['primary-hover']], ['white on error-solid', t['on-error-solid'], t['error-solid']],
    ...['ok', 'flat', 'sharp', 'error'].flatMap((n) => [[`${n} on bg`, t[n], t.bg], [`${n} on surface`, t[n], t.surface], [`${n} on its soft tint`, t[n], soft(n)]]),
  ];
  const nonText = [
    ['control edge on bg', t['line-strong'], t.bg], ['control edge on surface', t['line-strong'], t.surface],
    ['focus ring on bg', t.accent, t.bg], ['focus ring on surface', t.accent, t.surface],
    ...['ok', 'sharp', 'error'].map((n) => [`${n} status dot on surface`, t[n], t.surface]),
  ];
  test(`${mode}: text has at least 4.5:1 contrast`, () => {
    for (const [name, fg, bg] of text) assert.ok(ratio(fg, bg) >= 4.5, `${name}: ${ratio(fg, bg).toFixed(2)}:1`);
  });
  test(`${mode}: controls, focus ring and status dots have at least 3:1 contrast`, () => {
    for (const [name, fg, bg] of nonText) assert.ok(ratio(fg, bg) >= 3, `${name}: ${ratio(fg, bg).toFixed(2)}:1`);
  });
}

test('tap targets are at least 44px, in the buttons, nav, chips and segmented control', () => {
  assert.match(appCss, /--tap:\s*44px/);
  for (const [css, selector] of [[appCss, /\nnav a \{[^}]*min-height: var\(--tap\)/], [appCss, /\nbutton \{[^}]*min-height: var\(--tap\)/],
    [componentsCss, /\n\.btn \{[^}]*min-height: var\(--tap\)/], [componentsCss, /\n\.chip \{[^}]*min-height: var\(--tap\)/],
    [componentsCss, /\n\.segmented > :is\(button, label, a\) \{[^}]*min-height: var\(--tap\)/]]) assert.match(css, selector);
  assert.doesNotMatch(componentsCss, /min-height: (?:2|3)\d{1}px/);
});

test('the card surfaces leave a .segmented control alone (no double surface on the score screen)', () => {
  assert.doesNotMatch(appCss, /:not\(\.tabs\)/);
  assert.match(appCss, /main > div:not\(:empty\):not\(\.segmented\)/);
});

test('text uses four sizes and the system font stack', () => {
  assert.match(appCss, /--fs-caption: 13px; --fs-body: 16px; --fs-headline: 20px; --fs-title: 28px;/);
  assert.match(appCss, /--font-display: var\(--font-body\)/);
});
