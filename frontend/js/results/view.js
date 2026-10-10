// Renders a finished analysis: the six parts of the results screen.
//   1 can't-tell message + transposition  2 tier 1 and coach sentences  3 problem bars
//   4 media (and the form flag slot)      5 plan exercises             6 'How the AI worked'
import { takeMediaUrl } from '../api.js';
import { element } from '../dom.js';
import { state } from '../state.js';
import { createBarList } from './bars.js';
import { createJumper } from './jumper.js';
import { buildMeasurementIndex } from './measurements.js';
import { createMediaPlayer, isVideoTake } from './media.js';
import { renderPlan, renderTraceLink } from './plan.js';
import { renderSentenceList } from './sentences.js';
import { renderStopped } from './status.js';
import { renderTranspositionControl } from './transposition.js';

export const FALLBACK_TEXT = 'AI coach unavailable; showing measured results.';
export const FAILED_DEFAULT_TEXT = 'The take could not be checked. Please record it again.';
const CANT_TELL_DEFAULT_TEXT = "I couldn't tell how that went from this recording. Play it again slowly and clearly, and I'll listen once more.";
const CANT_TELL_HINT = 'If the notes were right but the app heard them in another key, change the transposition and it will check again.';

export function renderFailed(view, analysis) {
  renderStopped(view, { heading: 'This take could not be checked', message: analysis.error?.message ?? FAILED_DEFAULT_TEXT });
}

function cantTellMessage(feedback) {
  return feedback.sentences?.[0]?.text ?? CANT_TELL_DEFAULT_TEXT;
}

function renderCantTell(view, { analysis, feedback, plan }, { sessionId, rerun }) {
  const control = renderTranspositionControl({ sessionId, current: analysis.transposition?.semitones ?? 0, onChanged: rerun });
  const extra = element('div', '', 'cant-tell-extra');
  extra.append(element('p', CANT_TELL_HINT, 'muted'), control);
  renderStopped(view, { heading: "I couldn't tell", message: cantTellMessage(feedback), extra });
  view.append(renderPlan(plan));
  if (feedback.id) view.append(renderTraceLink(feedback.id));
}

// The tier 1 sentences are the measured results; in fallback mode the coach's sentences repeat them, so drop the repeats.
function coachSentences(feedback, tier1) {
  const measured = new Set(tier1.map((sentence) => sentence.text));
  return (feedback.sentences ?? []).filter((sentence) => !(feedback.mode === 'fallback' && measured.has(sentence.text)));
}

function sentenceSection(title, className, sentences, jumpContext, options) {
  const section = element('section', '', className);
  section.append(element('h2', title), renderSentenceList(sentences, jumpContext, options));
  return section;
}

// data: { analysis, feedback, plan }. context: { sessionId, take, rerun }.
// Returns the jump context ({ index, jumper }) and the pieces later features attach to.
export function renderDone(view, data, context) {
  const { analysis, feedback, plan } = data;
  state.current_feedback_id = feedback.id ?? null;
  if (analysis.cant_tell || feedback.cant_tell) return renderCantTell(view, data, context);

  const video = isVideoTake(analysis, state.take_setup.kind);
  const player = createMediaPlayer({ video, url: takeMediaUrl(context.sessionId, context.take) });
  const barList = createBarList(analysis);
  const jumpContext = { index: buildMeasurementIndex(analysis), jumper: createJumper({ player, barList }) };

  view.replaceChildren(element('h1', 'Results'));
  if (feedback.mode === 'fallback') view.append(element('p', FALLBACK_TEXT, 'notice fallback-notice', { role: 'status' }));
  const tier1 = analysis.tier1 ?? [];
  if (tier1.length) view.append(sentenceSection('What I measured', 'tier1', tier1, jumpContext));
  const coach = coachSentences(feedback, tier1);
  if (coach.length) view.append(sentenceSection("Your coach's notes", 'coach', coach, jumpContext, { checkedBadge: true }));
  if (!tier1.length && !coach.length) view.append(element('p', 'No problems were found in this take.', 'muted'));
  view.append(barList.section, player.section, renderPlan(plan));
  if (feedback.id) view.append(renderTraceLink(feedback.id));
  return { ...jumpContext, player, barList, analysis, feedback };
}
