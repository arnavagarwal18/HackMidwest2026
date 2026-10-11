// The step list shown while a take is being checked: Uploading, Finding notes, Matching key and bars, Writing feedback.
// The back end reports no percentage, so the current step comes from the analysis stage (status / form_status).
import { element } from '../dom.js';
import { STAGES } from './load.js';

export const WAIT_STEPS = ['Uploading', 'Finding notes', 'Matching key and bars', 'Writing feedback'];

const STEP_OF_STAGE = {
  [STAGES.processing]: 1,
  [STAGES.transcribed]: 2,
  [STAGES.formCheck]: 2,
  [STAGES.feedback]: 3,
};

// The take is already uploaded by the time the results screen asks for it, so the first step is always done here.
export function currentStep(stage) {
  return STEP_OF_STAGE[stage] ?? 1;
}

export function renderStepList(stage) {
  const current = currentStep(stage);
  const list = element('ol', '', 'wait-steps');
  WAIT_STEPS.forEach((label, index) => {
    const state = index < current ? 'done' : index === current ? 'current' : 'pending';
    const item = element('li', label, `wait-step ${state}`, { 'data-state': state });
    if (state === 'current') item.setAttribute('aria-current', 'step');
    list.append(item);
  });
  return list;
}
