// The clips recorded for one calibration, kept in memory (never in the DOM) so a banner or a failed upload loses nothing.
export const NOTE_COUNT = 3;
export const REF_SECONDS = 3; // each reference note
export const DELAY_SECONDS = 2; // the click test
export const CLICK_AFTER_S = 0.5; // the click plays this long after the delay recording starts

const indexName = (prefix, index) => `${prefix}_${index}`;

export function createClipStore() {
  const ref = Array(NOTE_COUNT).fill(null);
  const instrument = Array(NOTE_COUNT).fill(null);
  let click = null;

  return {
    setRef(index, clip) { ref[index] = clip; },
    clearRef(index) { ref[index] = null; },
    hasRef: (index) => ref[index] !== null,
    setInstrument(index, clip) { instrument[index] = clip; },
    hasInstrument: (index) => instrument[index] !== null,
    setClick(clip) { click = clip; },
    hasClick: () => click !== null,
    allRefs: () => ref.every(Boolean),
    ready: () => ref.every(Boolean) && click !== null,
    // The multipart parts of POST .../calibration and click_at_s (seconds from the delay recording's start to the click).
    toUpload() {
      if (!this.ready()) throw new Error('Record the three notes and the delay test before sending.');
      const files = { click: click.file };
      ref.forEach((clip, i) => { files[indexName('ref', i)] = clip.file; });
      instrument.forEach((clip, i) => { if (clip) files[indexName('inst', i)] = clip.file; });
      return { files, clickAtS: click.click_at_s };
    },
  };
}
