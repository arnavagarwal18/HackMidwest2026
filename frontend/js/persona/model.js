// Pure rules for the coach style (persona): the order of the options, the texts shown, and the tempo a persona presets.
import { TEMPO_RANGE } from '../take/setup.js';

export const DEFAULT_PERSONA = 'standard'; // the persona of a session that has none
export const FALLBACK_COACH_TEXT = 'No AI coach connected: showing the built-in feedback';
export const FEEDBACK_PENDING_TEXT = 'Feedback is still being made';
export const PICKER_LABEL = 'What are you practicing?';
export const SWITCH_LABEL = 'Coach'; // the menu button reads 'Coach: Standard'
export const STYLE_MENU_LABEL = 'Coach style';

export const coachedByText = (label) => `Coached by ${label}`;
export const nowCoachingText = (label) => `Now coaching: ${label}`;

// The default persona first (Standard), the rest in the order the back end sent them.
export function orderPersonas(personas, defaultId) {
  return [...personas].sort((a, b) => Number(b.id === defaultId) - Number(a.id === defaultId));
}

export const findPersona = (personas, id) => personas?.find((persona) => persona.id === id) ?? null;

// The words for a persona id; the id itself when the list does not know it, so a record is never shown without a name.
export const personaLabel = (personas, id) => findPersona(personas, id)?.label ?? id;

// The tempo the Play screen presets: written_factor x the written tempo, or the fixed_bpm; always a whole number inside
// the allowed range. persona.tempo is { kind: 'written_factor' | 'fixed_bpm', value }; null when it says nothing usable (then the field is left alone).
export function presetTempo(persona, writtenTempoBpm) {
  const { kind, value } = persona?.tempo ?? {};
  if (!Number.isFinite(value)) return null;
  const bpm = kind === 'fixed_bpm' ? value : kind === 'written_factor' && Number.isFinite(writtenTempoBpm) ? value * writtenTempoBpm : null;
  return bpm === null ? null : Math.min(TEMPO_RANGE.max, Math.max(TEMPO_RANGE.min, Math.round(bpm)));
}
