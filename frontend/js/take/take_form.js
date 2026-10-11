// The take setup form: the tempo stepper and the "Add camera" toggle up front; bars, count-in and metronome under "More options".
// Its values are read on demand, so a banner or a failed upload never clears what the learner typed.
import { button, el } from '../score/ui.js';
import { COUNT_IN_RANGE, TEMPO_RANGE } from './setup.js';

const HEADPHONES_NOTE = "Use headphones if on, so the clicks don't reach the mic.";
const TEMPO_STEP = 2;

function numberField(label, name, value, { min, max, step = 1 }) {
  const input = el('input', { attrs: { type: 'number', name, min, max, step, required: '' } });
  input.value = value;
  return { input, row: el('label', { className: 'field', children: [el('span', { text: label }), input] }) };
}

// setup: from initialSetup(); bars: the score's bar count; onKindChange(kind) runs when the camera is switched on or off;
// onTempoChange(bpm) runs when the learner sets a tempo inside the allowed range.
export function createTakeForm({ setup, bars, onKindChange, onTempoChange = () => {} }) {
  const barFrom = numberField('Bar from', 'bar_from', setup.bar_from, { min: 1, max: bars });
  const barTo = numberField('Bar to', 'bar_to', setup.bar_to, { min: 1, max: bars });
  const tempo = numberField('Tempo (beats per minute)', 'tempo_bpm', setup.tempo_bpm, { ...TEMPO_RANGE, step: 'any' });
  const countIn = numberField('Count-in (beats)', 'count_in_beats', setup.count_in_beats, COUNT_IN_RANGE);
  const camera = el('input', { attrs: { type: 'checkbox', name: 'add_camera' } });
  camera.checked = setup.kind === 'video';
  const metronome = el('input', { attrs: { type: 'checkbox', name: 'metronome_on' } });
  metronome.checked = setup.metronome_on;

  const kind = () => (camera.checked ? 'video' : 'mic');
  camera.addEventListener('change', () => onKindChange(kind()));

  function announceTempo() {
    const bpm = tempo.input.valueAsNumber;
    if (Number.isFinite(bpm) && bpm >= TEMPO_RANGE.min && bpm <= TEMPO_RANGE.max) onTempoChange(bpm);
  }
  tempo.input.addEventListener('change', announceTempo);

  function nudgeTempo(direction) {
    const current = tempo.input.valueAsNumber;
    if (!Number.isFinite(current)) return; // the box is empty or not a number: nothing to step from
    tempo.input.valueAsNumber = Math.min(TEMPO_RANGE.max, Math.max(TEMPO_RANGE.min, current + direction * TEMPO_STEP));
    announceTempo();
  }
  const slower = button('\u2212', () => nudgeTempo(-1), 'stepper');
  slower.setAttribute('aria-label', 'Slower');
  const faster = button('+', () => nudgeTempo(1), 'stepper');
  faster.setAttribute('aria-label', 'Faster');
  const tempoRow = el('div', { className: 'tempo-stepper', children: [tempo.row, slower, faster] });

  const inputs = [barFrom.input, barTo.input, tempo.input, countIn.input, camera, metronome, slower, faster];
  const moreOptions = el('details', {
    className: 'take-more',
    children: [
      el('summary', { text: 'More options' }),
      el('div', { className: 'field-row', children: [barFrom.row, barTo.row, countIn.row] }),
      el('label', { className: 'choice', children: [metronome, ' Metronome clicks during the take'] }),
      el('p', { text: HEADPHONES_NOTE, className: 'muted' }),
    ],
  });

  const element = el('form', {
    className: 'take-form',
    attrs: { novalidate: '' },
    children: [tempoRow, el('label', { className: 'choice', children: [camera, ' Add camera'] }), moreOptions],
  });
  element.addEventListener('submit', (event) => event.preventDefault());

  return {
    element,
    // Puts a tempo in the field (a persona's preset) and remembers it like a typed one.
    setTempo(bpm) {
      tempo.input.value = bpm;
      onTempoChange(bpm);
    },
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
