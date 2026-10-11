// The summary at the top of the results: one headline sentence, then pitch and rhythm as separate scores and the bars to work on.
import { element } from '../dom.js';
import { stat } from '../ui/components.js';
import { countsDetail, problemBarCounts } from './bar_kinds.js';
import { headline, percent, pitchScore, rhythmScore, STRONG_PITCH, STRONG_RHYTHM } from './scores.js';

const LEGACY_TONES = { ok: 'good', error: 'bad' };

function scoreStat(value, label, tone, detail = '') {
  const box = stat(value, label, tone);
  const [valueNode, labelNode] = box.children;
  // The older class names stay (num, lbl, detail, good, bad): tests look the tiles up by them.
  valueNode.className += ' num';
  labelNode.className += ' lbl';
  if (LEGACY_TONES[tone]) box.className += ` ${LEGACY_TONES[tone]}`;
  if (detail) box.append(element('span', detail, 'stat-note detail'));
  return box;
}

const toneFor = (share, strong) => (share >= strong ? 'ok' : share < 0.6 ? 'error' : 'warn');

// Bars to work on are only red when the notes were weak too; form, timing and extra-note flags over strong pitch stay neutral.
const workTone = (counts, pitch) => (!counts.total ? 'ok' : pitch.share >= STRONG_PITCH ? '' : 'error');

// Returns the summary (headline + strip), or null when the analysis has no bars to count.
export function renderStatStrip(analysis) {
  const pitch = pitchScore(analysis);
  if (!pitch) return null;
  const rhythm = rhythmScore(analysis);
  const toWork = problemBarCounts(analysis);
  const summary = element('section', '', 'summary');
  const strip = element('div', '', 'score-strip', { role: 'group', 'aria-label': 'Summary of this take' });
  strip.append(scoreStat(percent(pitch.share), 'Pitch', toneFor(pitch.share, STRONG_PITCH), `${pitch.right} of ${pitch.expected} notes right`));
  if (rhythm) strip.append(scoreStat(percent(rhythm.share), 'Rhythm', toneFor(rhythm.share, STRONG_RHYTHM), `${rhythm.onTime} of ${rhythm.timed} on the beat`));
  strip.append(scoreStat(String(toWork.total), 'Bars to work on', workTone(toWork, pitch), countsDetail(toWork)));
  summary.append(element('p', headline(pitch, rhythm, toWork), 'headline'), strip);
  return summary;
}
