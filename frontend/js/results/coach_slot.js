// The coach panel's place on the results screen. It exists only while results are on screen: nothing is mounted while the take is
// being processed, after a failed analysis or when the results could not be loaded. Each mount gets a new #coach-root element, so removing
// the old one makes the panel's own listeners (which check root.isConnected) drop themselves.
import { element } from '../dom.js';

// layout: the element the results and the coach sit in. mountCoach(root) builds the panel in `root` and returns it.
// Returns { show(), hide() }; show() returns the panel (mounted once, then the same one) and hide() removes it.
export function createCoachSlot(layout, mountCoach) {
  let root = null;
  let panel = null;
  return {
    show() {
      if (!panel) {
        root = element('div', '', '', { id: 'coach-root' });
        layout.append(root);
        panel = mountCoach(root);
      }
      return panel;
    },
    hide() {
      root?.remove();
      root = null;
      panel = null;
    },
  };
}
