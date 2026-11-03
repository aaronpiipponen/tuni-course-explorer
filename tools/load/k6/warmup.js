// Warm one fresh stack with the workload's fixed warm-up bodies before a measured profile.
import http from 'k6/http';
import { fail } from 'k6';
import { workload, warmupRequest } from './lib.js';

export const options = {
  vus: 1,
  iterations: 1,
  discardResponseBodies: true,
  noConnectionReuse: true,
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    fail('BASE_URL is required');
  }
  const passes = workload.matrix.warmup_samples || 1;
  for (const item of workload.matrix.warmup) {
    const request = warmupRequest(item);
    for (let pass = 0; pass < passes; pass += 1) {
      const response = http.post(baseUrl + request.path, JSON.stringify(request.body), {
        headers: { 'Content-Type': 'application/json' },
        timeout: '300s',
      });
      if (response.status !== 200) {
        fail(item.label + ' answered ' + String(response.status));
      }
    }
  }
}
