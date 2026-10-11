// WCAG 2.x contrast ratios for the results-v2 palettes. Run: node frontend/dev/prototype/contrast.mjs
// Text pairs need 4.5:1; large text and UI parts (marked "ui") need 3:1. Anything lower is flagged. Exits 1 if anything is flagged.
const STATUS = {
  good: { fill: '#CDEFD8', border: '#30A46C' },
  okay: { fill: '#FBE7B5', border: '#B7791F' },
  work: { fill: '#F9D0CE', border: '#E5484D' },
};
const PALETTES = {
  a: { name: 'Paper & Sky', bg: '#F5F5F7', surface: '#FFFFFF', text: '#1D1D1F', secondary: '#6E6E73', border: '#E5E5EA', accent: '#0066CC' },
  b: { name: 'Warm Linen', bg: '#FAF8F5', surface: '#FFFFFF', text: '#2B2A28', secondary: '#6B6760', border: '#ECE7E0', accent: '#3D5A80' },
  c: { name: 'Mist Iris', bg: '#F4F6FB', surface: '#FFFFFF', text: '#1F2433', secondary: '#5B6478', border: '#E3E7F0', accent: '#5B5BD6' },
};
const WHITE = '#FFFFFF';

const channel = (hex, start) => {
  const value = parseInt(hex.slice(start, start + 2), 16) / 255;
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
};
const luminance = (hex) => 0.2126 * channel(hex, 1) + 0.7152 * channel(hex, 3) + 0.0722 * channel(hex, 5);
const ratio = (a, b) => {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
};

// [label, foreground, background, minimum ratio]
const pairsFor = (p) => [
  ['text / bg', p.text, p.bg, 4.5],
  ['text / surface', p.text, p.surface, 4.5],
  ['secondary / bg', p.secondary, p.bg, 4.5],
  ['secondary / surface', p.secondary, p.surface, 4.5],
  ['white / accent (button text)', WHITE, p.accent, 4.5],
  ['accent / surface (Focus here text)', p.accent, p.surface, 4.5],
  ['accent / bg (Focus here text)', p.accent, p.bg, 4.5],
  ['accent / border (play button on player, ui)', p.accent, p.border, 3],
  ...Object.entries(STATUS).flatMap(([level, { fill, border }]) => [
    [`text on ${level} fill`, p.text, fill, 4.5],
    [`${level} border / surface (ui)`, border, p.surface, 3],
  ]),
];

let flagged = 0;
for (const [key, palette] of Object.entries(PALETTES)) {
  console.log(`\nPalette ${key}: ${palette.name}`);
  console.log('pair'.padEnd(46) + 'ratio'.padStart(7) + '  need  result');
  for (const [label, foreground, background, minimum] of pairsFor(palette)) {
    const value = ratio(foreground, background);
    const pass = value >= minimum;
    if (!pass) flagged += 1;
    console.log(label.padEnd(46) + value.toFixed(2).padStart(7) + `  ${minimum.toFixed(1)}   ${pass ? 'ok' : 'FLAG'}`);
  }
}
console.log(`\n${flagged} pair(s) flagged`);
process.exit(flagged ? 1 : 0);
