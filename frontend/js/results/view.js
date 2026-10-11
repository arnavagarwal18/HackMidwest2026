// Renders a finished analysis: the six parts of the results screen.
//   1 can't-tell message + transposition  2 bar strip, tier 1 and coach sentences  3 problem bars
//   4 media (and the form flag slot)      5 plan exercises             6 'How the AI worked'
import { takeMediaUrl } from '../api.js';
import { button, element } from '../dom.js';
import { state } from '../state.js';
import { createBarList } from './bars.js';
import { createJumper } from './jumper.js';
import { renderBarActions } from './loop.js';
import { buildMeasurementIndex } from './measurements.js';
import { createMediaPlayer, isVideoTake } from './media.js';
import { renderCantTell } from './cant_tell.js';
import { renderDetectionChip } from './detection.js';
import { renderPlan, renderTraceLink } from './plan.js';
import { renderSentenceList } from './sentences.js';
import { renderStatStrip } from './stats.js';
import { createBarStrip } from './strip.js';
import { renderStopped } from './status.js';

export const FALLBACK_TEXT = 'AI coach unavailable; showing measured results.';
export const FAILED_DEFAULT_TEXT = 'The take could not be checked. Please record it again.';

// The one filled button on the results: the take screen keeps the bars, tempo and kind of this take, so it is the same settings.
function playAgainActions() {
  const actions = element('p', '', 'actions');
  actions.append(button('Play again', () => { window.location.hash = '#/take'; }, 'play-again primary'));
  return actions;
}

export function renderFailed(view, analysis) {
  renderStopped(view, { heading: 'This take could not be checked', message: analysis.error?.message ?? FAILED_DEFAULT_TEXT });
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

// data: { analysis, feedback, plan }. context: { sessionId, take, rerun, note }; note is the one line the automatic key search leaves.
// Returns the jump context ({ index, jumper }) and the pieces later features attach to.
export function renderDone(view, data, context) {
  const { analysis, feedback, plan } = data;
  state.current_feedback_id = feedback.id ?? null;
  if (analysis.cant_tell || feedback.cant_tell) return renderCantTell(view, data, context);

  const video = isVideoTake(analysis, state.take_setup.kind);
  const player = createMediaPlayer({ video, url: takeMediaUrl(context.sessionId, context.take) });
  const renderActions = (bar) => renderBarActions(bar, { plan, analysis });
  const barList = createBarList(analysis, renderActions);
  const jumpContext = { index: buildMeasurementIndex(analysis), jumper: createJumper({ player, barList }) };
  const barStrip = createBarStrip(analysis, { ...jumpContext, renderActions });

  view.replaceChildren(element('h1', 'Results'));
  if (context.note) view.append(element('p', context.note, 'notice autokey-note', { role: 'status' }));
  if (feedback.mode === 'fallback') view.append(element('p', FALLBACK_TEXT, 'notice fallback-notice', { role: 'status' }));
  view.append(renderDetectionChip(analysis, { sessionId: context.sessionId, onChanged: context.rerun }));
  const stats = renderStatStrip(analysis);
  if (stats) view.append(stats);
  view.append(playAgainActions());
  if (barStrip) view.append(barStrip.section);
  const tier1 = analysis.tier1 ?? [];
  if (tier1.length) view.append(sentenceSection('What I measured', 'tier1', tier1, jumpContext));
  const coach = coachSentences(feedback, tier1);
  if (coach.length) view.append(sentenceSection("Your coach's notes", 'coach', coach, jumpContext, { checkedBadge: true }));
  if (!tier1.length && !coach.length) view.append(element('p', 'No problems were found in this take.', 'muted'));
  view.append(barList.section, player.section, renderPlan(plan));
  if (feedback.id) view.append(renderTraceLink(feedback.id));
  return { ...jumpContext, player, barList, barStrip, analysis, feedback };
}
