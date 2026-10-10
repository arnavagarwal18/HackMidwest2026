// Fetches what the results screen needs: the analysis and, once it is done, the feedback and plan.
import { ApiError, getAnalysis, getFeedback } from '../api.js';

export const STAGES = {
  processing: 'Hearing notes',
  transcribed: 'Checking against the score',
  formCheck: 'Checking form',
  feedback: 'Writing feedback',
};

// The one place that knows the shape of GET .../feedback. The back end sends the feedback with the plan inside it
// ({ ...feedback, plan }); an earlier mock wrapped them as { feedback, plan }. Either way: { feedback, plan }.
export function unwrapFeedback(body) {
  if (body.feedback) return { feedback: body.feedback, plan: body.plan ?? null };
  const { plan = null, ...feedback } = body;
  return { feedback, plan };
}

// The stage to show while the analysis is not done (analysis has status and form_status, no stage of its own).
export function stageLabel(analysis) {
  if (analysis.status === 'processing') return STAGES.processing;
  if (analysis.status === 'transcribed') return STAGES.transcribed;
  if (analysis.form_status === 'processing') return STAGES.formCheck;
  return STAGES.feedback; // diagnosed, or done with the feedback still being written
}

// One poll step: { done, analysis, feedback?, plan? }. Failed analysis is done (the screen shows its error);
// a done analysis whose feedback answers 409 wrong_state ('Feedback not ready.') is not done yet.
export async function fetchResultsOnce(sessionId, take) {
  const analysis = await getAnalysis(sessionId, take);
  if (analysis.status === 'failed') return { done: true, analysis };
  if (analysis.status !== 'done') return { done: false, analysis };
  try {
    return { done: true, analysis, ...unwrapFeedback(await getFeedback(sessionId, take)) };
  } catch (err) {
    if (err instanceof ApiError && err.code === 'wrong_state') return { done: false, analysis };
    throw err;
  }
}
