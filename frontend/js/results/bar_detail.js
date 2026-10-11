// What shows under the Bar by bar grid for the selected bar: its word, what was off (glyphs and words), its counts and drift,
// why it was flagged, the sentences about it, "Play this bar" when the recording has a time for it, and the loop actions of a flagged bar.
import { button, element } from '../dom.js';
import { addBarDetail } from './bars.js';
import { LEVEL_WORDS } from './bar_level.js';
import { resolveId, resolveJump } from './measurements.js';
import { reasonsForBar } from './problem_reasons.js';
import { renderSentenceList } from './sentences.js';

// The sentences whose jump lands in this bar.
function sentencesAbout(bar, sentences, index) {
  return sentences.filter((sentence) => resolveJump(sentence.jump, index)?.bar === bar.bar);
}

// "Play this bar" seeks the recording to the bar's first note; null when the take has no time for the bar.
function playButton(bar, { index, jumper }) {
  const place = resolveId(bar.id, index);
  if (typeof place?.time_s !== 'number') return null;
  const play = button('Play this bar', () => jumper.jumpTo(place, { select: false }), 'play-bar secondary btn');
  play.setAttribute('data-bar', String(bar.bar));
  return play;
}

// context: { analysis, jumpContext, sentences, renderActions }. look: { verdict, level, flagged } for this bar.
export function renderBarDetail(bar, { verdict, level, flagged }, { analysis, jumpContext, sentences, renderActions }) {
  const parts = [
    element('h3', `Bar ${bar.bar} · ${LEVEL_WORDS[level]}`, 'bar-detail-title'),
    element('p', `${verdict.glyph} ${verdict.words}`, 'bar-detail-verdict'),
    addBarDetail(element('div', '', 'bar-detail-body'), bar),
  ];
  const reasons = reasonsForBar(analysis, bar);
  if (reasons.length) parts.push(element('p', `Flagged: ${reasons.join('; ')}`, 'bar-reason'));
  const about = sentencesAbout(bar, sentences, jumpContext.index);
  if (about.length) parts.push(renderSentenceList(about, jumpContext));
  const actions = element('div', '', 'bar-detail-actions');
  const play = playButton(bar, jumpContext);
  if (play) actions.append(play);
  if (flagged) actions.append(renderActions(bar));
  parts.push(actions);
  return parts;
}
