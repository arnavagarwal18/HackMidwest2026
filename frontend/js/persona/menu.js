// A small menu button: 'Coach: Standard ▾' opens a list where exactly one option is chosen. Options come from the caller.
// createMenu({ label, menuLabel, options: [{ id, label, hint }], value, onChange(id) }) -> { element, setValue(id), setDisabled(flag) }.
// A choice calls onChange once; setValue changes the choice without calling it (to put a choice back).
// Keyboard: Enter, Space or an arrow opens it; arrows, Home and End move; Enter or Space chooses; Escape closes and returns to the button.
import { element } from '../dom.js';
import { loadPersonaStyles } from './styles.js';

const MOVES = { ArrowDown: 1, ArrowUp: -1 };

export function createMenu({ label, menuLabel, options, value, onChange }) {
  loadPersonaStyles();
  let chosen = value;
  let isOpen = false;
  let hadFocus = false;
  const trigger = element('button', '', 'coach-menu-button', { type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false' });
  const triggerText = element('span', '', 'coach-menu-text');
  trigger.append(triggerText, element('span', ' ▾', 'coach-menu-caret', { 'aria-hidden': 'true' }));
  const list = element('ul', '', 'coach-menu-list', { role: 'menu', 'aria-label': menuLabel });
  list.hidden = true;
  const items = options.map((option) => {
    const item = element('button', '', 'coach-menu-item', { type: 'button', role: 'menuitemradio', tabindex: '-1' });
    item.append(element('span', option.label, 'coach-menu-item-label'));
    if (option.hint) item.append(element('span', option.hint, 'coach-menu-item-hint muted'));
    item.addEventListener('click', () => choose(option.id));
    const entry = element('li', '', 'coach-menu-entry', { role: 'none' });
    entry.append(item);
    list.append(entry);
    return item;
  });
  const root = element('div', '', 'coach-menu');
  root.append(trigger, list);

  const labelOf = (id) => options.find((option) => option.id === id)?.label ?? id;

  function draw() {
    triggerText.textContent = `${label}: ${labelOf(chosen)}`;
    items.forEach((item, index) => item.setAttribute('aria-checked', String(options[index].id === chosen)));
  }

  const closeOnOutsideClick = (event) => { if (!root.contains?.(event.target)) close(); };

  function open(startAt = options.findIndex((option) => option.id === chosen)) {
    isOpen = true;
    list.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    document.addEventListener('click', closeOnOutsideClick);
    items[Math.max(0, startAt)]?.focus?.();
  }

  function close({ returnFocus = false } = {}) {
    if (!isOpen) return;
    isOpen = false;
    list.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', closeOnOutsideClick);
    if (returnFocus) trigger.focus?.();
  }

  function choose(id) {
    close({ returnFocus: true });
    if (id === chosen) return;
    chosen = id;
    draw();
    onChange(id);
  }

  function moveFocus(event, from) {
    const step = MOVES[event.key];
    const target = step ? (from + step + items.length) % items.length : { Home: 0, End: items.length - 1 }[event.key];
    if (target === undefined) return;
    event.preventDefault?.();
    items[target].focus?.();
  }

  trigger.addEventListener('click', () => (isOpen ? close() : open()));
  trigger.addEventListener('keydown', (event) => {
    if (!MOVES[event.key]) return;
    event.preventDefault?.();
    open(event.key === 'ArrowUp' ? items.length - 1 : undefined);
  });
  items.forEach((item, index) => item.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
      event.preventDefault?.();
      event.stopPropagation?.(); // the sheet around the menu stays open
      close({ returnFocus: true });
    } else if (event.key === 'Tab') close();
    else moveFocus(event, index);
  }));

  draw();
  return {
    element: root,
    setValue(id) { chosen = id; draw(); },
    // A disabled button loses focus; when enabled again it takes focus back if the page has none.
    setDisabled(flag) {
      if (flag) {
        close();
        hadFocus = document.activeElement === trigger;
      }
      trigger.disabled = flag;
      if (!flag && hadFocus && (!document.activeElement || document.activeElement === document.body)) trigger.focus?.();
      if (!flag) hadFocus = false;
    },
  };
}
