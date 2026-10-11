// The suggested-question chips under the coach's opening line. Tapping one sends that question.
// createSuggestions({ onPick(question) }) -> { element, show(questions), setDisabled(flag) }.
import { button, element } from '../dom.js';

export function createSuggestions({ onPick }) {
  const root = element('div', '', 'coach-chips', { role: 'group', 'aria-label': 'Suggested questions' });
  let disabled = false;

  const chipFor = (question) => {
    const chip = button(question, () => onPick(question), 'chip coach-chip');
    chip.disabled = disabled;
    return chip;
  };

  return {
    element: root,
    show(questions) {
      root.replaceChildren(...questions.map(chipFor));
      root.hidden = questions.length === 0;
    },
    setDisabled(flag) {
      disabled = flag;
      [...root.children].forEach((chip) => { chip.disabled = flag; });
    },
  };
}
