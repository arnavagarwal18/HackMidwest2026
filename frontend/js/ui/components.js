// Tiny builders for the shared components in css/components.css. Text is always set as text, never HTML.
import { element } from '../dom.js';

export const BADGE_TONES = ['ok', 'warn', 'error', 'neutral'];

function assertOneOf(value, allowed, what) {
  if (!allowed.includes(value)) throw new Error(`Unknown ${what} "${value}"; use one of: ${allowed.join(', ')}.`);
}

// badge('Complete', 'ok') -> <span class="badge badge-ok">Complete</span>
export function badge(text, tone = 'neutral') {
  assertOneOf(tone, BADGE_TONES, 'badge tone');
  return element('span', text, `badge badge-${tone}`);
}

// stat('87%', 'In tune') -> <div class="stat"><span class="stat-value">87%</span><span class="stat-label">In tune</span></div>
export function stat(value, label, tone = '') {
  if (tone) assertOneOf(tone, ['ok', 'warn', 'error'], 'stat tone');
  const box = element('div', '', tone ? `stat stat-${tone}` : 'stat');
  box.append(element('span', String(value), 'stat-value'), element('span', label, 'stat-label'));
  return box;
}

// emptyState('Nothing yet', 'Play a piece and it shows up here.') -> a dashed frame with a title and one line of help.
export function emptyState(title, help = '') {
  const box = element('div', '', 'empty-state');
  box.append(element('p', title, 'empty-state-title'));
  if (help) box.append(element('p', help));
  return box;
}

// skeleton(3) -> a block of three pulsing lines for content that is loading.
export function skeleton(lines = 3) {
  const box = element('div', '', '', { 'aria-hidden': 'true' });
  for (let i = 0; i < lines; i += 1) box.append(element('span', '', 'skeleton skeleton-line'));
  return box;
}

// pageHeader({ title, subtitle, steps: ['Choose', 'Play', 'Review'], currentStep: 1 }); currentStep counts from 0.
export function pageHeader({ title, subtitle = '', steps = [], currentStep = 0 }) {
  const header = element('div', '', 'page-header');
  const text = element('div', '', 'page-header-text');
  text.append(element('h1', title, 'page-title'));
  if (subtitle) text.append(element('p', subtitle, 'page-subtitle'));
  header.append(text);
  if (steps.length) {
    if (currentStep < 0 || currentStep >= steps.length) throw new Error(`currentStep ${currentStep} is outside the ${steps.length} steps.`);
    const list = element('ol', '', 'steps', { 'aria-label': 'Steps' });
    steps.forEach((label, index) => {
      const item = element('li', label, index < currentStep ? 'is-done' : '');
      if (index === currentStep) item.setAttribute('aria-current', 'step');
      list.append(item);
    });
    header.append(list);
  }
  return header;
}
