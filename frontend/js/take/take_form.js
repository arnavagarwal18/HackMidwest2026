// The take setup form: bars, tempo, mic or video, count-in and metronome. Its values are read on demand,
// so a banner or a failed upload never clears what the learner typed.
import { el } from '../score/ui.js';
import { COUNT_IN_RANGE, TEMPO_RANGE } from './setup.js';

const HEADPHONES_NOTE = "Use headphones if on, so the clicks don't reach the mic.";

function numberField(label, name, value, { min, max, step = 1 }) {
  const input = el('input', { attrs: { type: 'number', name, min, max, step, required: '' } });
  input.value = value;
  return { input, row: el('label', { className: 'field', children: [el('span', { text: label }), input] }) };
}

function choice(name, value, label, checked) {
  const input = el('input', { attrs: { type: 'radio', name, value } });
  input.checked = checked;
  return { input, label: el('label', { className: 'choice', children: [input, ` ${label}`] }) };
}

// setup: from initialSetup(); bars: the score's bar count; onKindChange(kind) runs when mic/video is switched.
export function createTakeForm({ setup, bars, onKindChange }) {
  const barFrom = numberField('Bar from', 'bar_from', setup.bar_from, { min: 1, max: bars });
  const barTo = numberField('Bar to', 'bar_to', setup.bar_to, { min: 1, max: bars });
  const tempo = numberField('Tempo (beats per minute)', 'tempo_bpm', setup.tempo_bpm, { ...TEMPO_RANGE, step: 'any' });
  const countIn = numberField('Count-in (beats)', 'count_in_beats', setup.count_in_beats, COUNT_IN_RANGE);
  const mic = choice('kind', 'mic', 'Microphone only', setup.kind === 'mic');
  const video = choice('kind', 'video', 'Video (camera and microphone)', setup.kind === 'video');
  const metronome = el('input', { attrs: { type: 'checkbox', name: 'metronome_on' } });
  metronome.checked = setup.metronome_on;
  const inputs = [barFrom.input, barTo.input, tempo.input, countIn.input, mic.input, video.input, metronome];

  const kind = () => (video.input.checked ? 'video' : 'mic');
  [mic.input, video.input].forEach((input) => input.addEventListener('change', () => onKindChange(kind())));

  const element = el('form', {
    className: 'take-form',
    attrs: { novalidate: '' },
    children: [
      el('div', { className: 'field-row', children: [barFrom.row, barTo.row, tempo.row, countIn.row] }),
      el('fieldset', { children: [el('legend', { text: 'Record with' }), mic.label, video.label] }),
      el('label', { className: 'choice', children: [metronome, ' Metronome clicks during the take'] }),
      el('p', { text: HEADPHONES_NOTE, className: 'muted' }),
    ],
  });
  element.addEventListener('submit', (event) => event.preventDefault());

  return {
    element,
    read: () => ({
      bar_from: barFrom.input.valueAsNumber,
      bar_to: barTo.input.valueAsNumber,
      tempo_bpm: tempo.input.valueAsNumber,
      count_in_beats: countIn.input.valueAsNumber,
      kind: kind(),
      metronome_on: metronome.checked,
    }),
    lock: (locked) => inputs.forEach((input) => { input.disabled = locked; }),
  };
}
