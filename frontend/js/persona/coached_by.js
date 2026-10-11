// "Coached by {label}" on the results, from the persona the feedback record names. Nothing is shown when the record names
// none or the persona list is not available (the coach style controls are hidden then, so there is nothing to explain).
import { element } from '../dom.js';
import { state } from '../state.js';
import { coachedByText, personaLabel } from './model.js';

export function renderCoachedBy(feedback) {
  if (!feedback.persona || !state.personas) return null;
  return element('p', coachedByText(personaLabel(state.personas, feedback.persona)), 'coached-by muted');
}
