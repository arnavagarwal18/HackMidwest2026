// The coach sheet shell, in one of two modes (setDocked switches between them):
// - sheet (narrow screens, the default): a modal bottom sheet that opens half height and can expand to full height.
//   It owns the window behaviour: open/close, Escape, focus in and back, a Tab trap, the grabber (tap or drag) and the backdrop.
//   Keys and focus are watched on the document while the sheet is open, so they still work when a control that had focus is disabled
//   (the browser then leaves focus on the page behind).
// - docked (wide screens): a non-modal complementary region, visible until collapsed. No backdrop, no Escape, no focus trap and no
//   document listeners. open() expands it and moves focus to initialFocus(); close() collapses it; the Close button reads Collapse.
// createSheet({ title, onClose, initialFocus }) -> { nodes, headerSlot, body, footer, open(), close(), isOpen(), isDocked(), setDocked(flag),
// contains(node), setExpanded(flag) }.
// The caller puts its content in headerSlot, body and footer, and appends `nodes` to its root.
import { button, element } from '../dom.js';

const DRAG_THRESHOLD_PX = 40;
const FOCUSABLE = 'button:not(:disabled), textarea:not(:disabled), [tabindex="0"]';

export function createSheet({ title, onClose = () => {}, initialFocus = () => null }) {
  let opened = false;
  let docked = false;
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
  const closeButton = button('Close', () => dismiss(), 'btn btn-ghost coach-close');
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
    if (docked) return openDocked();
    if (opened) return;
    opened = true;
    returnFocusTo = document.activeElement ?? null;
    setExpanded(false);
    backdrop.hidden = false;
    sheet.hidden = false;
    sheet.focus?.();
    document.addEventListener('keydown', onKeydown);
    document.addEventListener('focusin', pullFocusBack);
  }

  function stopListening() {
    document.removeEventListener('keydown', onKeydown);
    document.removeEventListener('focusin', pullFocusBack);
  }

  function close() {
    if (!opened) return;
    opened = false;
    backdrop.hidden = true;
    sheet.hidden = true;
    stopListening();
    returnFocusTo?.focus?.();
    returnFocusTo = null;
    onClose();
  }

  // Docked: showing the panel (again) is how the Ask coach button works, so it always moves focus to the question box.
  function openDocked() {
    opened = true;
    sheet.hidden = false;
    initialFocus()?.focus?.();
  }

  function collapse() {
    if (!opened) return;
    opened = false;
    sheet.hidden = true;
    onClose();
  }

  const dismiss = () => (docked ? collapse() : close());

  // Moves between the modes. Going docked drops the modal behaviour first (listeners, backdrop, focus memory) and shows the panel;
  // going back to a sheet leaves it closed, so a modal never appears over the page without being asked for.
  function setDocked(flag) {
    if (flag === docked) return;
    docked = flag;
    stopListening();
    returnFocusTo = null;
    backdrop.hidden = true;
    opened = docked;
    sheet.hidden = !docked;
    grabber.hidden = docked;
    sheet.className = docked ? 'coach-sheet is-docked' : 'coach-sheet';
    sheet.setAttribute('role', docked ? 'complementary' : 'dialog');
    if (docked) {
      sheet.removeAttribute('aria-modal');
      sheet.removeAttribute('tabindex');
    } else {
      sheet.setAttribute('aria-modal', 'true');
      sheet.setAttribute('tabindex', '-1');
      setExpanded(false);
    }
    closeButton.textContent = docked ? 'Collapse' : 'Close';
  }

  const contains = (node) => Boolean(node) && sheet.contains(node);

  // Keeps Tab inside the open sheet (aria-modal): from the last control it goes to the first, and back.
  // With focus outside the sheet (lost to the page), Tab goes to the first control, shift+Tab to the last.
  function trapTab(event) {
    const controls = [...(sheet.querySelectorAll?.(FOCUSABLE) ?? [])].filter((control) => !control.closest?.('[hidden]'));
    if (!controls.length) return;
    const edge = event.shiftKey ? controls[0] : controls.at(-1);
    const target = event.shiftKey ? controls.at(-1) : controls[0];
    if (contains(document.activeElement) && document.activeElement !== edge && document.activeElement !== sheet) return;
    event.preventDefault?.();
    target.focus?.();
  }

  function onKeydown(event) {
    if (event.key === 'Escape') { event.preventDefault?.(); close(); }
    else if (event.key === 'Tab') trapTab(event);
  }

  function pullFocusBack(event) {
    if (!contains(event.target)) sheet.focus?.();
  }

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
  return { nodes: [backdrop, sheet], headerSlot, body, footer, open, close: dismiss, isOpen: () => opened, isDocked: () => docked, setDocked, contains, setExpanded };
}
