// Turns the check records into a markdown table (one row per screen, a column per mode) and a list of every problem found.
import { hasProblems } from './check_screen.mjs';
import { rapidProblems } from './rapid_nav.mjs';

const cell = (record) => {
  if (!record) return 'n/a';
  if (!hasProblems(record)) return record.expectedFailedRequests.length || record.expectedConsoleErrors.length ? 'OK (only the expected failure)' : 'OK';
  const counts = [
    ['blank screen', record.blank ? 1 : 0], ['redirect', record.redirectedTo ? 1 : 0], ['load timeout', record.loadError ? 1 : 0], ['console errors', record.consoleErrors.length],
    ['warnings', record.consoleWarnings.length], ['exceptions', record.exceptions.length], ['failed requests', record.failedRequests.length],
  ].filter(([, n]) => n);
  return `ERR: ${counts.map(([label, n]) => `${n} ${label}`).join(', ')}`;
};

export function summaryTable(records) {
  const names = [...new Set(records.map((r) => r.name))];
  const find = (name, mode) => records.find((r) => r.name === name && r.mode === mode);
  const rows = names.map((name) => `| ${name} | ${cell(find(name, 'mock'))} | ${cell(find(name, 'real'))} |`);
  return ['| Screen | Mock | Real |', '|---|---|---|', ...rows].join('\n');
}

export function problemList(records) {
  return records.filter(hasProblems).map((r) => {
    const lines = [
      ...(r.blank ? ['blank screen'] : []), ...(r.redirectedTo ? [`redirected to ${r.redirectedTo}`] : []), ...(r.loadError ? [`load: ${r.loadError}`] : []),
      ...r.exceptions.map((e) => `exception: ${e}`), ...r.consoleErrors.map((e) => `console.error: ${e}`),
      ...r.consoleWarnings.map((e) => `console.warn: ${e}`), ...r.failedRequests.map((e) => `request: ${e}`),
    ];
    return `${r.name} [${r.mode}] (rendered: ${r.heading ?? r.textSnippet ?? 'nothing'}${r.bannerText ? `; banner: ${r.bannerText}` : ''})\n  ${lines.join('\n  ')}`;
  }).join('\n');
}

export const countOutcomes = (records) => ({ ok: records.filter((r) => !hasProblems(r)).length, withErrors: records.filter(hasProblems).length });

// Everything that should make the run fail: screens with problems, a rapid-navigation problem, or a run that did not cover every screen.
export function runProblems({ records, rapid, expectedScreens, expectedRapid }) {
  const incomplete = [
    ...(records.length < expectedScreens ? [`INCOMPLETE: only ${records.length} of ${expectedScreens} screen loads were checked`] : []),
    ...(rapid.length < expectedRapid ? [`INCOMPLETE: only ${rapid.length} of ${expectedRapid} rapid-navigation runs finished`] : []),
  ];
  const screens = records.filter(hasProblems).map((r) => `${r.name} [${r.mode}] has problems`);
  return [...incomplete, ...screens, ...rapid.flatMap(rapidProblems)];
}
