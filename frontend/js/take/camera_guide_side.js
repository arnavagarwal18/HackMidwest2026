// The side-on outline for the camera guide. Drawn for a learner facing the left of the picture
// (the camera sees their left side); a learner facing right gets the same shapes mirrored.
const VIEW_WIDTH = 160;
const MIRROR = `translate(${VIEW_WIDTH} 0) scale(-1 1)`;

const SIDE_BODY = [
  { tag: 'circle', attrs: { cx: 82, cy: 22, r: 10 } }, // head
  { tag: 'path', attrs: { d: 'M84 32 L84 40' } }, // neck
  { tag: 'path', attrs: { d: 'M72 90 Q70 60 74 46 Q84 38 94 46 Q97 62 94 90' } }, // chest, shoulder and back
];

const SIDE_INSTRUMENT_SHAPES = {
  trumpet: [
    { tag: 'path', attrs: { d: 'M83 46 L81 64 L60 33' } }, // near arm, hand at the valves
    { tag: 'rect', attrs: { x: 42, y: 22, width: 36, height: 9, rx: 4 }, area: true }, // trumpet pointing forward
  ],
};

// The shapes for one instrument seen from the side; `nearSide` is 'left' or 'right'.
export function sideGuideParts(instrument, nearSide) {
  const parts = [...SIDE_BODY, ...(SIDE_INSTRUMENT_SHAPES[instrument] || [])];
  if (nearSide === 'left') return parts;
  return parts.map((part) => ({ ...part, attrs: { ...part.attrs, transform: MIRROR } }));
}
