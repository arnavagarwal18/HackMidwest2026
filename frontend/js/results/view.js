// Renders a finished analysis, top to bottom: the recording, the verdict (results/hero.js), Bar by bar (results/strip.js),
// Practice next (results/plan.js), then quiet tap-to-open rows: The numbers (scores, key) and Detailed feedback (with the trace link).
// The can't-tell state (results/cant_tell.js) has none of these.
import { takeMediaUrl } from '../api.js';
import { element } from '../dom.js';
import { state } from '../state.js';
import { emptyState } from '../ui/components.js';
import { createJumper } from './jumper.js';
import { renderBarActions } from './loop.js';
import { buildMeasurementIndex } from './measurements.js';
import { createMediaPlayer, isVideoTake } from './media.js';
import { renderCantTell } from './cant_tell.js';
import { renderDetectionChip } from './detection.js';
import { renderHero } from './hero.js';
import { renderPracticeNext, renderTraceLink } from './plan.js';
import { disclosureRow } from './rows.js';
import { renderSentenceList } from './sentences.js';
import { renderStatStrip } from './stats.js';
import { createBarStrip } from './strip.js';
import { renderStopped } from './status.js';

export const FALLBACK_TEXT = 'AI coach unavailable; showing measured results.';
export const FAILED_DEFAULT_TEXT = 'The take could not be checked. Please record it again.';

export function renderFailed(view, analysis) {
  renderStopped(view, { heading: 'This take could not be checked', message: analysis.error?.message ?? FAILED_DEFAULT_TEXT });
}

// { tier1, coach }: the tier 1 sentences are the measured results; in fallback mode the coach's sentences repeat them, so drop the repeats.
function feedbackSentences(feedback, analysis) {
  const tier1 = analysis.tier1 ?? [];
  const measured = new Set(tier1.map((sentence) => sentence.text));
  const coach = (feedback.sentences ?? []).filter((sentence) => !(feedback.mode === 'fallback' && measured.has(sentence.text)));
  return { tier1, coach };
}

// The sentences of one kind (a list with its own small title), for the "Detailed feedback" row.
function sentenceSection(title, className, sentences, jumpContext) {
  const section = element('section', '', className);
  section.append(element('h3', title), renderSentenceList(sentences, jumpContext));
  return section;
}

// The measured sentences, the coach's notes, the fallback notice and the 'How the AI worked' link, in one row.
function feedbackRow(feedback, { tier1, coach }, jumpContext) {
  const parts = [];
  if (feedback.mode === 'fallback') parts.push(element('p', FALLBACK_TEXT, 'notice fallback-notice', { role: 'status' }));
  if (tier1.length) parts.push(sentenceSection('What I measured', 'tier1', tier1, jumpContext));
  if (coach.length) parts.push(sentenceSection("Your coach's notes", 'coach', coach, jumpContext));
  if (!tier1.length && !coach.length) parts.push(emptyState('Nothing to fix', 'No problems were found in this take.'));
  if (feedback.id) parts.push(renderTraceLink(feedback.id));
  return disclosureRow('Detailed feedback', 'feedback-row', parts);
}

// The scores in numbers, then the key and bars the back end used (with Change).
function numbersRow(analysis, { sessionId, rerun }) {
  const parts = [];
  const stats = renderStatStrip(analysis);
  if (stats) parts.push(stats);
  parts.push(renderDetectionChip(analysis, { sessionId, onChanged: rerun }));
  return disclosureRow('The numbers', 'numbers-row', parts);
}

// data: { analysis, feedback, plan }. context: { sessionId, take, rerun }.
// Returns the jump context ({ index, jumper }) and the pieces later features attach to.
export function renderDone(view, data, context) {
  const { analysis, feedback, plan } = data;
  state.current_feedback_id = feedback.id ?? null;
  if (analysis.cant_tell || feedback.cant_tell) return renderCantTell(view, data, context);

  const video = isVideoTake(analysis, state.take_setup.kind);
  const player = createMediaPlayer({ video, url: takeMediaUrl(context.sessionId, context.take) });
  const sentences = feedbackSentences(feedback, analysis);
  let barStrip = null; // a jump selects the bar's box, once the boxes exist (they need the jumper too)
  const barBoxes = { select: (barNumber, options) => barStrip?.select(barNumber, options) };
  const jumpContext = { index: buildMeasurementIndex(analysis), jumper: createJumper({ player, barBoxes }) };
  const renderActions = (bar) => renderBarActions(bar, { plan, analysis });
  barStrip = createBarStrip(analysis, { jumpContext, sentences: [...sentences.tier1, ...sentences.coach], renderActions });
  const goToBar = { canShow: (barNumber) => Boolean(barStrip?.hasBar(barNumber)), show: (barNumber) => barBoxes.select(barNumber, { reveal: true }) };
  const practiceNext = renderPracticeNext(plan, goToBar);

  view.replaceChildren(player.section, renderHero(analysis));
  if (barStrip) view.append(barStrip.section);
  if (practiceNext) view.append(practiceNext);
  view.append(numbersRow(analysis, context), feedbackRow(feedback, sentences, jumpContext));
  return { ...jumpContext, player, barStrip, analysis, feedback };
}
