// The summary at the top of the results: one headline sentence, then pitch and rhythm as separate scores and the bars to fix.
import { element } from '../dom.js';
import { problemBars } from './bars.js';
import { headline, percent, pitchScore, rhythmScore, STRONG_PITCH, STRONG_RHYTHM } from './scores.js';

function stat(value, label, tone = '', detail = '') {
  const box = element('div', '', `stat ${tone}`.trim());
  box.append(element('div', value, 'num'), element('div', label, 'lbl'));
  if (detail) box.append(element('div', detail, 'lbl detail'));
  return box;
}

const toneFor = (share, strong) => (share >= strong ? 'good' : share < 0.6 ? 'bad' : '');

// Returns the summary (headline + strip), or null when the analysis has no bars to count.
export function renderStatStrip(analysis) {
  const pitch = pitchScore(analysis);
  if (!pitch) return null;
  const rhythm = rhythmScore(analysis);
  const toFix = problemBars(analysis).length;
  const summary = element('section', '', 'summary');
  const strip = element('div', '', 'score-strip', { role: 'group', 'aria-label': 'Summary of this take' });
  strip.append(stat(percent(pitch.share), 'Pitch', toneFor(pitch.share, STRONG_PITCH), `${pitch.right} of ${pitch.expected} notes right`));
  if (rhythm) strip.append(stat(percent(rhythm.share), 'Rhythm', toneFor(rhythm.share, STRONG_RHYTHM), `${rhythm.onTime} of ${rhythm.timed} on the beat`));
  strip.append(stat(String(toFix), 'Bars to fix', toFix ? 'bad' : 'good'));
  summary.append(element('p', headline(pitch, rhythm), 'headline'), strip);
  return summary;
}
