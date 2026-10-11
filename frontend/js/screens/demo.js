// Demo upload (#/demo, not in the nav): pick a sheet-music photo and a video, press Start, and the app runs the normal flow
// (score reading, score check, take upload, results) as if a user had taken the photo and recorded the take.
import { clearBanner, reportError } from '../banner.js';
import { createPicks, picksProblem } from '../demo/picks.js';
import { runDemo } from '../demo/flow.js';
import { createDemoView } from '../demo/view.js';
import { button, el, loadScoreStyles } from '../score/ui.js';

const INTRO = 'For demos: choose a photo of sheet music and a video of someone playing it. Start runs the normal steps; you only confirm the score.';

export function render(root, _params, isCurrent = () => true) {
  loadScoreStyles();
  const view = createDemoView();
  const picks = createPicks({ onChange: () => clearBanner() });
  const start = button('Start', begin, 'primary');

  async function begin() {
    clearBanner();
    const chosen = picks.read();
    const problem = picksProblem(chosen);
    if (problem) return reportError(new Error(problem));
    start.disabled = true;
    try {
      const hash = await runDemo({ ...chosen, view, isCurrent });
      if (hash) window.location.hash = hash;
    } catch (err) {
      reportError(err);
      view.setStatus('The demo stopped. Fix the problem above, then press Start to begin again.');
    } finally {
      start.disabled = false;
    }
  }

  root.append(el('section', { className: 'demo', children: [
    el('h1', { text: 'Demo upload' }),
    el('p', { text: INTRO, className: 'muted' }),
    picks.element,
    el('p', { children: [start] }),
    view.element,
  ] }));
}
