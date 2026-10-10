// Plays one reference tone at a time: a sine at the exact Hz, gain 0.5, with 20 ms fades so it does not click.
// Stopping never waits on the audio clock (a suspended or interrupted phone context freezes it): the auto-stop is a
// wall-clock timer, and stopAll() silences the tone directly and then suspends the context.
import { getAudioContext } from '../audio.js';

export const AUTO_STOP_S = 10; // a tone stops by itself after this long unless Hold is on
export const FADE_S = 0.02;
export const TONE_GAIN = 0.5;

// onChange(noteName | null) runs whenever the playing note changes (the page highlights its button).
// onError(err) gets every failure to stop cleanly; the tone is silenced anyway.
export function createTonePlayer({ getContext = getAudioContext, onChange = () => {}, onError = () => {} } = {}) {
  let current = null; // { note, osc, gain }
  let context = null; // the AudioContext of the last tap, so stopAll() can reach it without a tap
  let hold = false;
  let autoStopTimer = null;
  let stopCount = 0; // counts stop() calls, so a tap still waiting for the context cannot start a tone after a Stop

  function report(message, err) {
    console.error(message, err);
    onError(new Error(message));
  }

  function clearAutoStop() {
    clearTimeout(autoStopTimer);
    autoStopTimer = null;
  }

  function armAutoStop() {
    clearAutoStop();
    if (hold) return;
    autoStopTimer = setTimeout(() => stop().catch((err) => report('The tone did not stop on time. Press Stop.', err)), AUTO_STOP_S * 1000);
  }

  // Ends the playing voice: with the 20 ms fade for a tap, at once (gain 0) for the Stop button and for leaving the page.
  // Every step runs even if an earlier one fails, so a broken node never leaves the others sounding.
  function silenceVoice({ immediate }) {
    const voice = current;
    current = null;
    clearAutoStop();
    if (!voice) return false;
    const now = context.currentTime;
    const param = voice.gain.gain;
    const end = immediate ? now : now + FADE_S;
    const steps = [
      () => param.cancelScheduledValues(now),
      () => param.setValueAtTime(immediate ? 0 : param.value, now),
      () => !immediate && param.linearRampToValueAtTime(0, end),
      () => voice.osc.stop(end),
    ];
    steps.forEach((step) => {
      try {
        step();
      } catch (err) {
        report('The tone could not be stopped cleanly. Press Stop, or close this page.', err);
      }
    });
    return true;
  }

  async function suspendContext() {
    if (context && context.state === 'running') await context.suspend();
  }

  function startVoice(note) {
    const start = context.currentTime;
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.type = 'sine';
    osc.frequency.value = note.hz;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(TONE_GAIN, start + FADE_S);
    osc.connect(gain).connect(context.destination);
    const voice = { note, osc, gain };
    osc.onended = () => {
      gain.disconnect();
      if (current === voice) {
        current = null;
        onChange(null);
      }
    };
    osc.start(start);
    current = voice;
    armAutoStop();
  }

  // Silences everything at once and suspends the context. Safe to call when nothing plays. Always ends with the UI showing "stopped".
  async function stop() {
    stopCount += 1;
    silenceVoice({ immediate: true });
    onChange(null);
    try {
      await suspendContext();
    } catch (err) {
      report('The audio could not be paused, but the tone is silent.', err);
    }
  }

  return {
    // A tap on a note: stops the note that is playing (and stops there if it was the same note), else starts this one.
    // The first call creates the AudioContext, so it must come from a tap.
    async toggle(note) {
      const stopsBefore = stopCount;
      context = await getContext();
      if (stopCount !== stopsBefore) {
        await suspendContext(); // Stop came while the context was waking up: stay silent
        return;
      }
      const wasSame = current !== null && current.note.name === note.name;
      silenceVoice({ immediate: false });
      if (wasSame) {
        onChange(null);
        return;
      }
      startVoice(note);
      onChange(note.name);
    },
    stop,
    // Hold keeps the tone playing until Stop or a tap on the note. Turning it off re-arms the 10 s auto-stop from that moment.
    setHold(value) {
      hold = value;
      if (current) armAutoStop();
    },
    isHolding: () => hold,
    playing: () => (current ? current.note.name : null),
  };
}
