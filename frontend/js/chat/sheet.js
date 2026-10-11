// The coach sheet shell: a bottom sheet (centred on wide screens) that opens half height and can expand to full height.
// It owns only the window behaviour: open/close, Escape, focus in and back, a Tab trap, the grabber (tap or drag) and the backdrop.
// createSheet({ title, onClose }) -> { nodes, headerSlot, body, footer, open(), close(), isOpen(), setExpanded(flag) }.
// The caller puts its content in headerSlot, body and footer, and appends `nodes` to its root.
import { button, element } from '../dom.js';

const DRAG_THRESHOLD_PX = 40;
const FOCUSABLE = 'button:not(:disabled), textarea:not(:disabled), [tabindex="0"]';

export function createSheet({ title, onClose = () => {} }) {
  let opened = false;
  let expanded = false;
  let returnFocusTo = null;

  const backdrop = element('div', '', 'coach-backdrop');
  const grabber = element('button', '', 'coach-grabber', { type: 'button', 'aria-expanded': 'false' });
  grabber.append(element('span', '', 'coach-grabber-bar'));
  const header = element('header', '', 'coach-head');
  const body = element('div', '', 'coach-body');
  const footer = element('div', '', 'coach-foot');
  const sheet = element('section', '', 'coach-sheet', { role: 'dialog', 'aria-modal': 'true', 'aria-label': title, tabindex: '-1' });
  sheet.append(grabber, header, body, footer);
  const closeButton = button('Close', () => close(), 'btn btn-ghost coach-close');
  const headerSlot = element('div', '', 'coach-head-slot'); // the caller's header content, before the Close button
  header.append(headerSlot, closeButton);
  backdrop.hidden = true;
  sheet.hidden = true;

  function setExpanded(flag) {
    expanded = flag;
    sheet.setAttribute('data-size', flag ? 'full' : 'half');
    grabber.setAttribute('aria-expanded', String(flag));
    grabber.setAttribute('aria-label', flag ? 'Make the coach smaller' : 'Make the coach bigger');
  }

  function open() {
    if (opened) return;
    opened = true;
    returnFocusTo = document.activeElement ?? null;
    setExpanded(false);
    backdrop.hidden = false;
    sheet.hidden = false;
    sheet.focus?.();
  }

  function close() {
    if (!opened) return;
    opened = false;
    backdrop.hidden = true;
    sheet.hidden = true;
    returnFocusTo?.focus?.();
    returnFocusTo = null;
    onClose();
  }

  // Keeps Tab inside the open sheet (aria-modal): from the last control it goes to the first, and back.
  function trapTab(event) {
    const controls = [...(sheet.querySelectorAll?.(FOCUSABLE) ?? [])].filter((control) => !control.closest?.('[hidden]'));
    if (!controls.length) return;
    const edge = event.shiftKey ? controls[0] : controls.at(-1);
    const target = event.shiftKey ? controls.at(-1) : controls[0];
    if (document.activeElement !== edge && document.activeElement !== sheet) return;
    event.preventDefault?.();
    target.focus?.();
  }

  sheet.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.preventDefault?.(); close(); }
    else if (event.key === 'Tab') trapTab(event);
  });
  backdrop.addEventListener('click', () => close());

  let dragFrom = null;
  let dragged = false;
  grabber.addEventListener('pointerdown', (event) => { dragFrom = event.clientY; dragged = false; });
  grabber.addEventListener('pointercancel', () => { dragFrom = null; });
  grabber.addEventListener('pointerup', (event) => {
    if (dragFrom === null) return;
    const moved = event.clientY - dragFrom;
    dragFrom = null;
    if (Math.abs(moved) < DRAG_THRESHOLD_PX) return; // a tap: the click handler toggles
    dragged = true;
    if (moved < 0) setExpanded(true);
    else if (expanded) setExpanded(false);
    else close();
  });
  grabber.addEventListener('click', () => {
    if (dragged) { dragged = false; return; }
    setExpanded(!expanded);
  });

  setExpanded(false);
  return { nodes: [backdrop, sheet], headerSlot, body, footer, open, close, isOpen: () => opened, setExpanded };
}
