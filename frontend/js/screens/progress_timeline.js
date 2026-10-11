// The progress timeline: a compact summary on top, then one dot and card per event, oldest first, each with a popover that explains it.
import { element } from '../dom.js';
import { stat } from '../ui/components.js';
import { KIND_TAKE, changeAgainstFirst, eventDetails, eventLabel, eventTone, summarise, takeNumbers, timeText } from './progress_events.js';

const ARROW = ' → ';
const bpmValue = (value) => (value == null ? 'none yet' : `${Math.round(value)} bpm`);
const fromTo = (first, latest, format, hasTwoTakes) => (hasTwoTakes ? `${format(first)}${ARROW}${format(latest)}` : format(first));

export function summaryStats(events, exercises) {
  const { first, latest, hasTwoTakes, exercisesDone, exerciseCount } = summarise(events, exercises);
  const row = element('div', '', 'timeline-summary', { role: 'group', 'aria-label': 'Summary' });
  if (first) {
    const improved = hasTwoTakes && latest.errors < first.errors;
    const suffix = hasTwoTakes ? 'first take → latest' : 'first take';
    row.append(
      stat(fromTo(first.errors, latest.errors, String, hasTwoTakes), `Errors, ${suffix}`, improved ? 'ok' : ''),
      stat(fromTo(first.clean_bpm, latest.clean_bpm, bpmValue, hasTwoTakes), `Clean tempo, ${suffix}`),
    );
  }
  row.append(stat(`${exercisesDone} of ${exerciseCount}`, 'Exercises completed', exerciseCount > 0 && exercisesDone === exerciseCount ? 'ok' : ''));
  return row;
}

function popover(id, event, firstTake) {
  const box = element('div', '', 'timeline-popover', { id, role: 'tooltip' });
  box.append(...eventDetails(event, firstTake).map((sentence) => element('p', sentence)));
  return box;
}

function timelineItem(event, index, number, firstTake) {
  const tipId = `timeline-tip-${index}`;
  const item = element('li', '', `timeline-item timeline-${eventTone(event)}`);
  const card = element('button', '', 'timeline-card', { type: 'button', 'aria-describedby': tipId, 'aria-expanded': 'false' });
  card.append(element('span', eventLabel(event, number), 'timeline-label'));
  const change = changeAgainstFirst(event, firstTake);
  if (change) card.append(element('span', change.text, `timeline-change timeline-change-${change.tone}`));
  const when = timeText(event);
  if (when) card.append(element('span', when, 'timeline-time'));
  item.append(element('span', '', 'timeline-dot', { 'aria-hidden': 'true' }), card, popover(tipId, event, firstTake));
  return { item, card };
}

// Tapping or pressing a card opens its popover (hover and focus open it in the stylesheet); Escape or tapping it again closes it.
function wirePopovers(entries) {
  const setOpen = (open, target) => entries.forEach(({ item, card }) => {
    const shown = open && item === target;
    item.classList.toggle('is-open', shown);
    card.setAttribute('aria-expanded', String(shown));
  });
  entries.forEach(({ item, card }) => {
    card.addEventListener('click', () => setOpen(!item.classList.contains('is-open'), item));
    card.addEventListener('keydown', (press) => { if (press.key === 'Escape') setOpen(false, item); });
  });
}

export function timeline(events) {
  const list = element('ol', '', 'timeline', { 'aria-label': 'Practice timeline, oldest first' });
  const firstTake = events.find((event) => event.kind === KIND_TAKE);
  const numbers = takeNumbers(events);
  const entries = events.map((event, index) => timelineItem(event, index, numbers[index], firstTake));
  wirePopovers(entries);
  list.append(...entries.map(({ item }) => item));
  return list;
}
