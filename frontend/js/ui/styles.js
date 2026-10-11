// Loads one screen's own stylesheet once. The shared sheets are linked from index.html; a screen with its own sheet calls this.
import { element } from '../dom.js';

export function loadStylesheet(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  document.head.append(element('link', '', '', { rel: 'stylesheet', href }));
}
