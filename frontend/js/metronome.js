// Metronome clicks on the Web Audio clock. A look-ahead loop schedules each click a little before it is due,
// so the timing is the audio clock's, not setInterval's.
const LOOK_AHEAD_S = 0.1;
const TICK_MS = 25;
const CLICK_S = 0.03;
const ACCENT_HZ = 1500;
const BEAT_HZ = 1000;

// One click at an exact AudioContext time. accent = the higher, louder click on beat 1.
export function scheduleClick(audioCtx, time, accent = false) {
  const osc = audioCtx.createOscillator();
  const gain = audioCtx.createGain();
  osc.frequency.value = accent ? ACCENT_HZ : BEAT_HZ;
  gain.gain.setValueAtTime(accent ? 1 : 0.6, time);
  gain.gain.exponentialRampToValueAtTime(0.001, time + CLICK_S);
  osc.connect(gain).connect(audioCtx.destination);
  osc.start(time);
  osc.stop(time + CLICK_S);
}

// Clicks every 60 / tempoBpm seconds from startTime; beat 0, beatsPerBar, ... are accented.
// maxBeats = Infinity keeps going until stop(); a finite number (the count-in) stops by itself.
// Returns { stop, nextBeatTime }. Beat times are startTime + n * 60 / tempoBpm exactly (no drift).
export function startMetronome({ audioCtx, tempoBpm, startTime, beatsPerBar = 4, maxBeats = Infinity }) {
  if (!(tempoBpm > 0)) {
    throw new Error(`Cannot start the metronome: tempo ${tempoBpm} is not a positive number.`);
  }
  const beatSeconds = 60 / tempoBpm;
  let beat = 0;
  const scheduleDue = () => {
    while (beat < maxBeats && startTime + beat * beatSeconds < audioCtx.currentTime + LOOK_AHEAD_S) {
      scheduleClick(audioCtx, startTime + beat * beatSeconds, beat % beatsPerBar === 0);
      beat += 1;
    }
    if (beat >= maxBeats) {
      clearInterval(timer);
    }
  };
  const timer = setInterval(scheduleDue, TICK_MS);
  scheduleDue();
  return {
    stop: () => clearInterval(timer),
    nextBeatTime: () => startTime + beat * beatSeconds,
  };
}
