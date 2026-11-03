// Run one steady mixed level with one heavy user per capacity.heavy_every users and light users
// for the rest.
import { buildOptions, defaultIteration, profileSummary } from './lib.js';

export const options = buildOptions('mixed');

export default function () {
  defaultIteration('mixed');
}

export function handleSummary(data) {
  return profileSummary('mixed', data);
}
