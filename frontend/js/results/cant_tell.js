// The "I couldn't tell" state: the back end's message, what was heard (note count, best match) and ONE next action chosen
// from the reason the back end gives (analysis.cant_tell_reason: low_match, few_pairs or too_short).
import { element } from '../dom.js';
import { renderPlan, renderTraceLink } from './plan.js';
import { percent } from './scores.js';
import { renderStopped } from './status.js';
import { renderTranspositionControl } from './transposition.js';

const CANT_TELL_DEFAULT_TEXT = "I couldn't tell how that went from this recording. Play it again slowly and clearly, and I'll listen once more.";
export const NEXT_ACTIONS = {
  low_match: 'Choose the key you played in, and I will check again.',
  few_pairs: 'Record again a little closer to the microphone, and play every note clearly.',
  too_short: 'Record again with a longer range of bars, so there are enough notes to check.',
};
const DEFAULT_ACTION = NEXT_ACTIONS.few_pairs;

// What the back end heard, as one line; null when it sent neither a note count nor a match.
export function heardText(analysis) {
  const notes = analysis.notes ?? [];
  const parts = [];
  if (notes.length) {
    const heard = notes.filter((note) => note.played_i != null).length + (analysis.extras ?? []).length;
    parts.push(`${heard} note${heard === 1 ? '' : 's'} heard`);
  }
  if (typeof analysis.alignment_quality === 'number') parts.push(`best match to the score ${percent(analysis.alignment_quality)}`);
  return parts.length ? `What I heard: ${parts.join(', ')}.` : null;
}

export function nextAction(analysis) {
  return NEXT_ACTIONS[analysis.cant_tell_reason] ?? DEFAULT_ACTION;
}

// The key control is always there; it is the one filled button only when the notes did not match (low_match), else Record again is.
const choosesKey = (analysis) => analysis.cant_tell_reason === 'low_match';

export function renderCantTell(view, { analysis, feedback, plan }, { sessionId, rerun, note }) {
  const extra = element('div', '', 'cant-tell-extra');
  if (note) extra.append(element('p', note, 'autokey-note'));
  const heard = heardText(analysis);
  if (heard) extra.append(element('p', heard, 'heard-summary'));
  extra.append(element('p', nextAction(analysis), 'next-action'));
  extra.append(renderTranspositionControl({ sessionId, current: analysis.transposition?.semitones ?? 0, onChanged: rerun, primary: choosesKey(analysis) }));
  const message = feedback.sentences?.[0]?.text ?? CANT_TELL_DEFAULT_TEXT;
  renderStopped(view, { heading: "I couldn't tell", message, extra, primaryRecord: !choosesKey(analysis) });
  view.append(renderPlan(plan));
  if (feedback.id) view.append(renderTraceLink(feedback.id));
}
