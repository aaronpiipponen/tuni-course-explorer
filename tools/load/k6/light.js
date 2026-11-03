// Run one steady light-only level with one stateful virtual user per simulated user.
import { buildOptions, defaultIteration, profileSummary } from './lib.js';

export const options = buildOptions('light_only');

export default function () {
  defaultIteration('light_only');
}

export function handleSummary(data) {
  return profileSummary('light_only', data);
}
