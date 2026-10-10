// The form flag list under the video: one row per flag; clicking it (or its time chip) jumps to the flag's peak.
import { button, element } from '../../dom.js';
import { resolveId } from '../measurements.js';
import { renderChip } from '../sentences.js';

// flags: analysis.form. jumpContext: { index, jumper }. Returns the list element, or null when there are no flags.
export function renderFlagList(flags, jumpContext) {
  if (!flags.length) return null;
  const list = element('ul', '', 'sentences form-flags');
  flags.forEach((flag) => {
    const item = element('li', '', 'sentence form-flag');
    item.append(button(flag.label, () => jumpContext.jumper.jumpTo(resolveId(flag.id, jumpContext.index)), 'sentence-text'), renderChip(flag.id, jumpContext));
    list.append(item);
  });
  return list;
}
