// Plays one reference tone at a time: a sine at the exact Hz, gain 0.5, with 20 ms fades so it does not click.
import { getAudioContext } from '../audio.js';

export const TONE_SECONDS = 4;
export const FADE_S = 0.02;
export const TONE_GAIN = 0.5;
export const HOLD_LIMIT_S = 3600; // a held tone still stops after an hour, so a forgotten phone goes quiet

// onChange(noteName | null) runs whenever the playing note changes (the page highlights its button).
export function createTonePlayer({ getContext = getAudioContext, onChange = () => {} } = {}) {
  let current = null; // { note, osc, gain, start }
  let hold = false;

  function fadeOutAt(voice, end) {
    voice.endAt = end;
    voice.gain.gain.setValueAtTime(TONE_GAIN, end - FADE_S);
    voice.gain.gain.linearRampToValueAtTime(0, end);
    voice.osc.stop(end);
  }

  function stopNow(ctx) {
    const voice = current;
    if (!voice) return;
    current = null;
    const now = ctx.currentTime;
    voice.gain.gain.cancelScheduledValues(now);
    voice.gain.gain.setValueAtTime(voice.gain.gain.value, now);
    voice.gain.gain.linearRampToValueAtTime(0, now + FADE_S);
    voice.osc.stop(now + FADE_S);
  }

  function startVoice(ctx, note) {
    const start = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.value = note.hz;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(TONE_GAIN, start + FADE_S);
    osc.connect(gain).connect(ctx.destination);
    const voice = { note, osc, gain, start };
    osc.onended = () => {
      gain.disconnect();
      if (current === voice) {
        current = null;
        onChange(null);
      }
    };
    osc.start(start);
    fadeOutAt(voice, start + (hold ? HOLD_LIMIT_S : TONE_SECONDS));
    current = voice;
  }

  return {
    // A tap on a note: stops the note that is playing (and stops there if it was the same note), else starts this one.
    // The first call creates the AudioContext, so it must come from a tap.
    async toggle(note) {
      const ctx = await getContext();
      const wasSame = current !== null && current.note.name === note.name;
      stopNow(ctx);
      if (wasSame) {
        onChange(null);
        return;
      }
      startVoice(ctx, note);
      onChange(note.name);
    },
    // Hold keeps the tone playing until it is tapped again. Switching it while a note plays changes that note too.
    async setHold(value) {
      hold = value;
      if (!current) return;
      const ctx = await getContext();
      const voice = current;
      if (!voice) return;
      voice.gain.gain.cancelScheduledValues(voice.endAt - FADE_S); // only the fade-out; the fade-in stays
      const end = voice.start + (hold ? HOLD_LIMIT_S : TONE_SECONDS);
      fadeOutAt(voice, Math.max(end, ctx.currentTime + FADE_S)); // letting go late ends the note right away
    },
    isHolding: () => hold,
    playing: () => (current ? current.note.name : null),
  };
}
