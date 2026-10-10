// The outline drawn over the camera preview: head, shoulders, arms and the instrument area.
// Everything about the shape lives here so the camera position can change in one place:
// the open question is front-on versus about 45 degrees, and today the outline is front-on.
export const CAMERA_POSITION = 'front';

const SVG_NS = 'http://www.w3.org/2000/svg';
const VIEW_BOX = '0 0 160 90'; // the preview is 16:9

// Each shape is an SVG path (or circle/ellipse) in VIEW_BOX units, as seen from the camera.
const BODY = [
  { tag: 'circle', attrs: { cx: 80, cy: 22, r: 10 } }, // head
  { tag: 'path', attrs: { d: 'M74 32 L74 38 M86 32 L86 38' } }, // neck
  { tag: 'path', attrs: { d: 'M48 90 L50 52 Q54 41 80 39 Q106 41 110 52 L112 90' } }, // shoulders and torso
];

const INSTRUMENT_SHAPES = {
  violin: [
    { tag: 'path', attrs: { d: 'M50 54 L36 40 L30 30' } }, // left arm up to the scroll
    { tag: 'path', attrs: { d: 'M110 54 L124 66 L100 58' } }, // bow arm, elbow out to the right
    { tag: 'ellipse', attrs: { cx: 66, cy: 36, rx: 16, ry: 5, transform: 'rotate(-25 66 36)' }, area: true }, // violin under the chin
  ],
  trumpet: [
    { tag: 'path', attrs: { d: 'M50 54 L44 66 L64 44' } }, // left arm, hand at the valves
    { tag: 'path', attrs: { d: 'M110 54 L116 66 L96 44' } }, // right arm, hand at the valves
    { tag: 'rect', attrs: { x: 64, y: 28, width: 32, height: 12, rx: 6 }, area: true }, // trumpet at the mouth
  ],
};

function shape({ tag, attrs, area }) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, value));
  if (area) node.classList.add('guide-instrument');
  return node;
}

// Returns an <svg> to lay over the preview. An instrument without its own shape gets the body only.
export function createCameraGuide(instrument) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', VIEW_BOX);
  svg.setAttribute('class', 'camera-guide');
  svg.setAttribute('aria-hidden', 'true');
  svg.dataset.position = CAMERA_POSITION;
  svg.dataset.instrument = INSTRUMENT_SHAPES[instrument] ? instrument : 'none';
  [...BODY, ...(INSTRUMENT_SHAPES[instrument] || [])].forEach((part) => svg.append(shape(part)));
  return svg;
}
