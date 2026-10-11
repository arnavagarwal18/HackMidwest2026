// The coach style controls keep their styles in their own file, loaded the way the Play screen loads take.css.
import { el } from '../score/ui.js';

const STYLE_HREF = 'css/persona.css';

export function loadPersonaStyles() {
  if (document.querySelector(`link[href="${STYLE_HREF}"]`)) return;
  document.head.append(el('link', { attrs: { rel: 'stylesheet', href: STYLE_HREF } }));
}
