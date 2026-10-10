// The tone page (frontend/tone.html): one big button per reference note, a Hold toggle and an always-visible Stop button, opened on a phone from the calibration QR code.
// URL: tone.html[?instrument=trumpet][&note=F4] (the instrument defaults to trumpet). No app shell; errors go to the red banner.
import { getReferenceNotes } from '../api.js';
import { reportError } from '../banner.js';
import { button, element } from '../dom.js';
import { stopWhenLeaving } from './lifecycle.js';
import { createTonePlayer } from './player.js';

export const formatHz = (hz) => (Number.isInteger(hz) ? hz.toFixed(1) : String(hz));
export const buttonLabel = (note) => `${note.name} - ${formatHz(note.hz)} Hz`;

export const DEFAULT_INSTRUMENT = 'trumpet'; // the app is trumpet only

export function readParams(search) {
  const params = new URLSearchParams(search);
  return { instrument: params.get('instrument') || DEFAULT_INSTRUMENT, askedNote: params.get('note') ?? '' };
}

export async function startTonePage(root, search = window.location.search) {
  const { instrument, askedNote } = readParams(search);
  let notes;
  try {
    notes = await getReferenceNotes(instrument);
  } catch (err) {
    reportError(err); // no notes, so no buttons; reload the page to try again
    return;
  }
  const noteButtons = new Map();
  const holdButton = button('Hold: off', () => toggleHold(), 'tone-hold');
  holdButton.setAttribute('aria-pressed', 'false');
  const player = createTonePlayer({
    onChange: (playing) => noteButtons.forEach((el, name) => {
      el.classList.toggle('playing', name === playing);
      el.setAttribute('aria-pressed', String(name === playing));
    }),
    onError: reportError,
  });
  stopWhenLeaving(player);

  async function guarded(action) {
    try {
      await action();
    } catch (err) {
      reportError(err);
    }
  }
  const toggleHold = () => guarded(async () => {
    const hold = !player.isHolding();
    player.setHold(hold);
    holdButton.textContent = `Hold: ${hold ? 'on' : 'off'}`;
    holdButton.setAttribute('aria-pressed', String(hold));
  });

  root.append(element('h1', 'Tone'));
  if (askedNote) root.append(element('p', `The app is asking for ${askedNote}.`, 'muted'));
  notes.forEach((note) => {
    const noteButton = button(buttonLabel(note), () => guarded(() => player.toggle(note)), 'tone-note');
    noteButton.setAttribute('aria-pressed', 'false');
    if (note.name === askedNote) noteButton.classList.add('asked');
    noteButtons.set(note.name, noteButton);
    root.append(noteButton);
  });
  root.append(holdButton, button('Stop', () => guarded(() => player.stop()), 'tone-stop'));
}
