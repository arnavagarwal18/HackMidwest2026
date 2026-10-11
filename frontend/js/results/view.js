// Renders a finished analysis. First glance: the hero (results/hero.js). Everything else sits behind quiet tap-to-open rows:
//   Bar by bar (strip)  Bars to work on (reasons)  The numbers (scores, key)  Detailed feedback  Your recording  Practice plan
// The can't-tell state (results/cant_tell.js) has no rows.
import { takeMediaUrl } from '../api.js';
import { element } from '../dom.js';
import { state } from '../state.js';
import { emptyState, pageHeader } from '../ui/components.js';
import { createBarList } from './bars.js';
import { createJumper } from './jumper.js';
import { renderBarActions } from './loop.js';
import { buildMeasurementIndex } from './measurements.js';
import { createMediaPlayer, isVideoTake } from './media.js';
import { renderCantTell } from './cant_tell.js';
import { renderDetectionChip } from './detection.js';
import { renderHero } from './hero.js';
import { renderPlan, renderTraceLink } from './plan.js';
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

// The tier 1 sentences are the measured results; in fallback mode the coach's sentences repeat them, so drop the repeats.
function coachSentences(feedback, tier1) {
  const measured = new Set(tier1.map((sentence) => sentence.text));
  return (feedback.sentences ?? []).filter((sentence) => !(feedback.mode === 'fallback' && measured.has(sentence.text)));
}

// The sentences of one kind (a list with its own small title), for the "Detailed feedback" row.
function sentenceSection(title, className, sentences, jumpContext) {
  const section = element('section', '', className);
  section.append(element('h3', title), renderSentenceList(sentences, jumpContext));
  return section;
}

// The measured sentences, the coach's notes, the fallback notice and the 'How the AI worked' link, in one row.
function feedbackRow(feedback, analysis, jumpContext) {
  const tier1 = analysis.tier1 ?? [];
  const coach = coachSentences(feedback, tier1);
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
  const renderActions = (bar) => renderBarActions(bar, { plan, analysis });
  const barList = createBarList(analysis, renderActions);
  const barsRow = disclosureRow('Bars to work on', 'bars-row', [barList.section]);
  // A jump to a bar opens the row that holds it, so the highlighted bar is on screen.
  const revealingList = { highlight: (bar) => { barsRow.open = true; barList.highlight(bar); } };
  const jumpContext = { index: buildMeasurementIndex(analysis), jumper: createJumper({ player, barList: revealingList }) };
  const barStrip = createBarStrip(analysis, { ...jumpContext, renderActions });

  view.replaceChildren(pageHeader({ title: 'Results' }), renderHero(analysis));
  if (barStrip) view.append(disclosureRow('Bar by bar', 'strip-row', [barStrip.section]));
  view.append(
    barsRow,
    numbersRow(analysis, context),
    feedbackRow(feedback, analysis, jumpContext),
    disclosureRow('Your recording', 'media-row', [player.section]),
    disclosureRow('Practice plan', 'plan-row', [renderPlan(plan, { heading: false })]),
  );
  return { ...jumpContext, player, barList, barStrip, analysis, feedback };
}
