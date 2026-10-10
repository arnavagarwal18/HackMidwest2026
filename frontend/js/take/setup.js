// The take setup values: defaults from the score, a check before recording, and the fields POST /takes expects.
export const TEMPO_RANGE = { min: 30, max: 240 };
export const COUNT_IN_RANGE = { min: 0, max: 8 };
export const DEFAULT_KIND = 'mic';

// score: { bars, tempo_bpm, time_signature }. saved: state.take_setup, whose null fields mean "not chosen yet"
// (the loop trainer may fill only the bars). One bar of count-in is the top number of the time signature.
export function initialSetup(score, saved = {}) {
  const [beatsPerBar] = score.time_signature || [4, 4];
  return {
    bar_from: saved.bar_from ?? 1,
    bar_to: saved.bar_to ?? score.bars,
    tempo_bpm: saved.tempo_bpm ?? score.tempo_bpm,
    kind: saved.kind ?? DEFAULT_KIND,
    count_in_beats: saved.count_in_beats ?? beatsPerBar,
    metronome_on: saved.metronome_on ?? false,
  };
}

// Returns a message the learner can act on, or null when the setup can be sent.
export function validateSetup(setup, bars) {
  const { bar_from: from, bar_to: to, tempo_bpm: tempo, count_in_beats: countIn } = setup;
  if (![from, to, tempo, countIn].every(Number.isFinite)) return 'Fill in the bars, tempo and count-in with numbers.';
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 1 || to > bars || from > to) {
    return `Pick whole bar numbers from 1 to ${bars}, with "from" not after "to".`;
  }
  if (tempo < TEMPO_RANGE.min || tempo > TEMPO_RANGE.max) return `Tempo must be between ${TEMPO_RANGE.min} and ${TEMPO_RANGE.max} beats per minute.`;
  if (!Number.isInteger(countIn) || countIn < COUNT_IN_RANGE.min || countIn > COUNT_IN_RANGE.max) {
    return `Count-in must be a whole number of beats from ${COUNT_IN_RANGE.min} to ${COUNT_IN_RANGE.max}.`;
  }
  return null;
}

// The text fields of POST /sessions/{id}/takes. An uploaded file has no downbeat_s, so the key is left out.
export function takeFields(setup, { kind, source, downbeatS }) {
  const fields = {
    kind,
    source,
    bar_from: setup.bar_from,
    bar_to: setup.bar_to,
    tempo_bpm: setup.tempo_bpm,
    count_in_beats: setup.count_in_beats,
  };
  if (source === 'recorded') fields.downbeat_s = downbeatS;
  return fields;
}

// 'video' for a video file, otherwise 'mic' (audio only).
export const kindOfFile = (file) => (file.type.startsWith('video/') ? 'video' : 'mic');
