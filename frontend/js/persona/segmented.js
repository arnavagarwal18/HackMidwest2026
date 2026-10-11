// A small segmented control: one row of options, exactly one chosen. Options come from the caller (never hard-coded here).
// createSegmented({ label, options: [{ id, label, hint }], value, onChange(id) }) -> { element, setValue(id), setDisabled(flag) }.
// A click chooses the option and then calls onChange; setValue changes the choice without calling it (to put a choice back).
import { element } from '../dom.js';
import { loadPersonaStyles } from './styles.js';

const ARROW_STEPS = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

export function createSegmented({ label, options, value, onChange }) {
  loadPersonaStyles();
  let chosen = value;
  const group = element('div', '', 'segmented', { role: 'radiogroup', 'aria-label': label });
  const buttons = options.map((option) => {
    const segment = element('button', option.label, 'segment', { type: 'button', role: 'radio', title: option.hint ?? '' });
    segment.addEventListener('click', () => choose(option.id));
    segment.addEventListener('keydown', (event) => moveWithArrows(event, option.id));
    return segment;
  });
  group.append(...buttons);

  function draw() {
    buttons.forEach((segment, index) => {
      const on = options[index].id === chosen;
      segment.setAttribute('aria-checked', String(on));
      segment.setAttribute('tabindex', on || (chosen === null && segment === buttons[0]) ? '0' : '-1');
      segment.className = on ? 'segment segment-on' : 'segment';
    });
  }

  function choose(id) {
    if (id === chosen) return;
    chosen = id;
    draw();
    onChange(id);
  }

  function moveWithArrows(event, fromId) {
    const step = ARROW_STEPS[event.key];
    if (!step) return;
    event.preventDefault?.();
    const index = options.findIndex((option) => option.id === fromId);
    const next = options[(index + step + options.length) % options.length];
    buttons[options.indexOf(next)].focus?.();
    choose(next.id);
  }

  draw();
  return {
    element: group,
    setValue(id) { chosen = id; draw(); },
    setDisabled(flag) { buttons.forEach((segment) => { segment.disabled = flag; }); group.setAttribute('aria-disabled', String(flag)); },
  };
}
