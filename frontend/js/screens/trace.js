import { getTrace, isNotFound } from '../api.js';
import { state } from '../state.js';
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

const seconds = (ms) => `${(ms / 1000).toFixed(2)}s`;

function eventRow(event) {
  const label = EVENT_LABELS[event.event] ?? { marker: event.event, verb: event.event };
  const row = element('li', '', `trace-event trace-${event.event}`);
  const title = [label.verb, label.bare ? null : event.name].filter(Boolean).join(' ');
  row.append(
    element('span', seconds(event.t_ms), 'trace-time'),
    element('span', label.marker, 'trace-marker'),
    element('span', title, 'trace-title'),
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
  const section = element('section', '', `trace-group agent-${agent}`);
  section.append(element('h3', AGENT_NAMES[agent] ?? agent));
  const list = element('ol', '', 'trace-events');
  list.append(...events.map(eventRow));
  section.append(list);
  return section;
}

// Pure view of one trace response; exported so it can be tried with any saved response.
export function renderTrace(root, trace) {
  root.replaceChildren(element('h1', 'Trace'));
  const modeText = trace.mode === 'ai'
    ? 'Written by the AI agents, then checked against your score.'
    : 'The AI could not be used, so the safe built-in text was shown.';
  root.append(element('p', modeText, 'trace-mode'));
  if (!trace.events.length) {
    root.append(element('p', 'No steps were recorded for this feedback.', 'empty-state'));
    return;
  }
  root.append(...groupByAgent(trace.events).map(agentGroup));
}

export const NO_TRACE_TEXT = 'No trace for this feedback yet.';

export async function render(root, { fb }, isCurrent = () => true) {
  let trace;
  try {
    trace = await getTrace(state.session_id ?? 'no-session', fb);
  } catch (err) {
    if (!isNotFound(err)) throw err; // other errors reach the banner
    if (!isCurrent()) return;
    console.warn(`No trace for feedback ${fb} (${err.code}).`);
    root.replaceChildren(element('h1', 'Trace'), element('p', NO_TRACE_TEXT, 'empty-state'));
    return;
  }
  if (!isCurrent()) return; // the learner already moved to another screen
  renderTrace(root, trace);
}
