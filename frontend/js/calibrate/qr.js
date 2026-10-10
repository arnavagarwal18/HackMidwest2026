// Draws a QR code as an SVG built from DOM nodes (no HTML strings). Needs vendor/qrcode.js (qrcode-generator), loaded by index.html.
const SVG_NS = 'http://www.w3.org/2000/svg';
const QUIET_ZONE = 4;

// The dark squares as one SVG path ("M x y h1 v1 h-1 z" per square), in module units.
export function qrPath(isDark, count) {
  const squares = [];
  for (let row = 0; row < count; row += 1) {
    for (let col = 0; col < count; col += 1) {
      if (isDark(row, col)) squares.push(`M${col + QUIET_ZONE} ${row + QUIET_ZONE}h1v1h-1z`);
    }
  }
  return squares.join('');
}

// Returns an <svg> for `text`, or throws if the library is missing or the text does not fit.
export function createQrSvg(text, qrcodeLib = window.qrcode) {
  if (!qrcodeLib) throw new Error('The QR code library did not load.');
  const qr = qrcodeLib(0, 'M'); // type 0: the smallest version that fits
  qr.addData(text);
  qr.make();
  const count = qr.getModuleCount();
  const size = count + 2 * QUIET_ZONE;
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `QR code for ${text}`);
  svg.setAttribute('shape-rendering', 'crispEdges');
  const background = document.createElementNS(SVG_NS, 'rect');
  background.setAttribute('width', size);
  background.setAttribute('height', size);
  background.setAttribute('fill', '#fff');
  const squares = document.createElementNS(SVG_NS, 'path');
  squares.setAttribute('d', qrPath((row, col) => qr.isDark(row, col), count));
  squares.setAttribute('fill', '#000');
  svg.append(background, squares);
  return svg;
}
