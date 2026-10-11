import { getTrace, isNotFound } from '../api.js';
import { state } from '../state.js';
import { badge, emptyState, pageHeader, skeleton } from '../ui/components.js';
import { loadStylesheet } from '../ui/styles.js';
import { element } from './placeholder.js';

// Trace screen (#/trace/:fb): what each agent did while writing one piece of feedback, in time order.
// Runs of events by the same agent form one coloured group.

const AGENT_NAMES = {
  orchestrator: 'Orchestrator', coach: 'Coach', planner: 'Planner', instructor: 'Instructor', checker: 'Checker', referee: 'Referee',
};

// Marker text is shown as well as colour, so pass and fail do not rely on colour alone.
const EVENT_LABELS = {
  model_start: { marker: 'Model', verb: 'asked the model', bare: true },
  model_end: { marker: 'Result', verb: 'the model answered', bare: true },
  model_error: { marker: 'Error', verb: 'the model call failed', bare: true },
  tool_start: { marker: 'Call', verb: 'called tool' },
  tool_end: { marker: 'Result', verb: 'got result from' },
  tool_error: { marker: 'Error', verb: 'tool failed:' },
  error: { marker: 'Error', verb: 'stopped with an error:' },
  check_pass: { marker: 'Pass', verb: 'check passed' },
  check_fail: { marker: 'Fail', verb: 'check failed' },
  dropped: { marker: 'Dropped', verb: 'dropped' },
  fallback: { marker: 'Fallback', verb: 'fell back to the safe text' },
};

// Badge tone per event: passes are green, failures red, and what was dropped or fell back amber.
const EVENT_TONES = { check_pass: 'ok', check_fail: 'error', model_error: 'error', tool_error: 'error', error: 'error', dropped: 'warn', fallback: 'warn' };

const seconds = (ms) => `${(ms / 1000).toFixed(2)}s`;

function eventRow(event) {
  const label = EVENT_LABELS[event.event] ?? { marker: event.event, verb: event.event };
  const row = element('li', '', `trace-event trace-${event.event}`);
  const title = [label.verb, label.bare ? null : event.name].filter(Boolean).join(' ');
  const marker = element('span', '', 'trace-marker');
  marker.append(badge(label.marker, EVENT_TONES[event.event] ?? 'neutral'));
  row.append(
    marker,
    element('span', title, 'trace-title'),
    element('span', seconds(event.t_ms), 'trace-time'),
  );
  if (event.duration_ms != null) row.append(element('span', `${event.duration_ms} ms`, 'muted trace-duration'));
  if (event.detail) row.append(element('p', event.detail, 'trace-detail'));
  return row;
}

// Splits events into runs of consecutive events from the same agent.
function groupByAgent(events) {
  const groups = [];
  for (const event of events) {
    const last = groups[groups.length - 1];
    if (last && last.agent === event.agent) last.events.push(event);
    else groups.push({ agent: event.agent, events: [event] });
  }
  return groups;
}

function agentGroup({ agent, events }) {
  const section = element('section', '', `trace-group card agent-${agent}`);
  const header = element('div', '', 'card-header');
  header.append(element('h3', AGENT_NAMES[agent] ?? agent), badge(`${events.length} ${events.length === 1 ? 'step' : 'steps'}`));
  const list = element('ol', '', 'trace-events');
  list.append(...events.map(eventRow));
  const body = element('div', '', 'card-body');
  body.append(list);
  section.append(header, body);
  return section;
}

// Pure view of one trace response; exported so it can be tried with any saved response.
export function renderTrace(root, trace) {
  root.replaceChildren(pageHeader({ title: 'Trace', subtitle: 'What each agent did while writing this feedback, in time order.' }));
  const modeText = trace.mode === 'ai'
    ? 'Written by the AI agents, then checked against your score.'
    : 'The AI could not be used, so the safe built-in text was shown.';
  const mode = element('p', '', 'trace-mode');
  mode.append(trace.mode === 'ai' ? badge('AI agents', 'ok') : badge('Built-in text', 'warn'), ` ${modeText}`);
  root.append(mode);
  if (!trace.events.length) {
    root.append(emptyState('No steps recorded', 'No steps were recorded for this feedback.'));
    return;
  }
  root.append(...groupByAgent(trace.events).map(agentGroup));
}

export const NO_TRACE_TEXT = 'No trace for this feedback yet.';

export async function render(root, { fb }, isCurrent = () => true) {
  loadStylesheet('css/trace.css');
  root.replaceChildren(pageHeader({ title: 'Trace' }), skeleton(4));
  let trace;
  try {
    trace = await getTrace(state.session_id ?? 'no-session', fb);
  } catch (err) {
    if (isCurrent()) root.replaceChildren(pageHeader({ title: 'Trace' })); // the placeholders must not stay up after a failure
    if (!isNotFound(err)) throw err; // other errors reach the banner
    if (!isCurrent()) return;
    console.warn(`No trace for feedback ${fb} (${err.code}).`);
    root.append(emptyState(NO_TRACE_TEXT));
    return;
  }
  if (!isCurrent()) return; // the learner already moved to another screen
  renderTrace(root, trace);
}
