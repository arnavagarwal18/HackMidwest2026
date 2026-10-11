// The page header of the setup screens: the learner's way in is Score -> Calibrate -> Play.
import { pageHeader } from './components.js';

export const FLOW_STEPS = ['Score', 'Calibrate', 'Play'];

// currentStep counts from 0 in FLOW_STEPS.
export const flowHeader = ({ title, subtitle, currentStep }) => pageHeader({ title, subtitle, steps: FLOW_STEPS, currentStep });
