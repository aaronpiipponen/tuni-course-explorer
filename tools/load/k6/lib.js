// Shared stateful user driver for the serving capacity profiles.
import http from 'k6/http';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';
import { Counter, Gauge, Trend } from 'k6/metrics';
import { sleep } from 'k6';

const workloadData = new SharedArray('workload', () => [
  JSON.parse(open('workload.json')),
]);
const payloadData = new SharedArray('payload', () => [
  JSON.parse(open('payload-context.json')),
]);
export const workload = workloadData[0];
export const payload = payloadData[0];

const baseUrl = __ENV.BASE_URL;
if (!baseUrl) {
  throw new Error('BASE_URL is required');
}

const requestDuration = new Trend('request_duration');
const refused429 = new Counter('refused_429');
const unexpectedStatus = new Counter('unexpected_status');
const transportFailure = new Counter('transport_failure');
const clockOffset = new Gauge('clock_offset_seconds');
let clockRecorded = false;

http.setResponseCallback(http.expectedStatuses(200, 429));

for (const groupID of workload.pool) {
  if (!payload.pool[groupID]) {
    throw new Error('the payload context is missing pool course ' + groupID);
  }
}
if (!Array.isArray(payload.study_roots) || payload.study_roots.length === 0) {
  throw new Error('the payload context holds no study roots');
}
const studyRootCeiling = Math.max(
  workload.users.light.study_roots,
  workload.users.heavy.study_roots,
);
if (payload.study_roots.length < studyRootCeiling) {
  throw new Error('the payload context holds fewer study roots than the workload needs');
}

const pauseMin = workload.users.think_time_seconds_min;
const pauseMax = workload.users.think_time_seconds_max;
if (
  !Number.isFinite(pauseMin)
  || !Number.isFinite(pauseMax)
  || pauseMin < 0
  || pauseMax < pauseMin
) {
  throw new Error('the workload pause range must be ordered and non-negative');
}

function hash32(seed, user) {
  let value = (seed ^ Math.imul(user, 0x9e3779b9)) >>> 0;
  value ^= value >>> 16;
  value = Math.imul(value, 0x7feb352d);
  value ^= value >>> 15;
  value = Math.imul(value, 0x846ca68b);
  value ^= value >>> 16;
  return value >>> 0;
}

function mulberry32(seed) {
  let state = seed >>> 0;
  return function next() {
    state = (state + 0x6d2b79f5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function classConfig(className) {
  const values = workload.users[className];
  if (!values) {
    throw new Error('the workload has no user class ' + className);
  }
  return values;
}

function pickSize(rng, values) {
  const span = values.basis_max - values.basis_min + 1;
  return values.basis_min + Math.floor(rng() * span);
}

function initialBasis(rng, className) {
  const values = classConfig(className);
  const size = pickSize(rng, values);
  const pool = Array.from({ length: workload.pool.length }, (_value, index) => index);
  for (let index = 0; index < size; index += 1) {
    const swap = index + Math.floor(rng() * (pool.length - index));
    const held = pool[index];
    pool[index] = pool[swap];
    pool[swap] = held;
  }
  return pool.slice(0, size).sort((left, right) => left - right);
}

function addCourse(user, rng) {
  if (user.basis.length >= workload.pool.length) {
    return;
  }
  const chosen = Math.floor(rng() * workload.pool.length);
  if (user.basis.includes(chosen)) {
    return;
  }
  user.basis.push(chosen);
  user.basis.sort((left, right) => left - right);
}

function removeCourse(user, rng) {
  if (user.basis.length <= 1) {
    return;
  }
  const chosen = Math.floor(rng() * user.basis.length);
  user.basis.splice(chosen, 1);
}

function chooseCourse(user, rng) {
  const fromBasis = user.basis.length > 0
    && rng() < workload.users.target_from_basis_probability;
  if (fromBasis) {
    return workload.pool[user.basis[Math.floor(rng() * user.basis.length)]];
  }
  return workload.pool[Math.floor(rng() * workload.pool.length)];
}

function chooseComparison(user, rng) {
  const first = chooseCourse(user, rng);
  let second = chooseCourse(user, rng);
  if (second === first) {
    second = workload.pool[(workload.pool.indexOf(first) + 1) % workload.pool.length];
  }
  return { first, second };
}

function entry(groupID) {
  const value = payload.pool[groupID];
  if (!value) {
    throw new Error('the payload context is missing ' + groupID);
  }
  return value;
}

function basisIds(user) {
  return user.basis.map((index) => workload.pool[index]);
}

function requestFor(operation, user, rng) {
  const language = workload.display_language;
  const values = classConfig(user.className);
  if (operation === 'search_title' || operation === 'search_code') {
    const includeInactive = rng() < values.inactive_probability;
    const groupID = workload.pool[Math.floor(rng() * workload.pool.length)];
    const course = entry(groupID);
    const text = operation === 'search_title'
      ? (course.title_en || course.title_fi)
      : course.code;
    if (!text) {
      throw new Error('the pool course ' + groupID + ' has no query text');
    }
    return {
      path: '/api/search',
      operation,
      body: {
        query: text,
        display_language: language,
        include_inactive: includeInactive,
      },
    };
  }
  if (operation === 'study_structure') {
    return {
      path: '/api/study-structure',
      operation,
      body: {
        root_group_ids: payload.study_roots.slice(0, values.study_roots),
        allow_unavailable: true,
      },
    };
  }
  if (operation === 'prerequisites') {
    const includeInactive = rng() < values.inactive_probability;
    return {
      path: '/api/prerequisites',
      operation,
      body: {
        target_code: chooseCourse(user, rng),
        selected_codes: basisIds(user),
        completed_codes: [],
        include_recommended: false,
        include_inferred: values.include_inferred,
        active_only: !includeInactive,
      },
    };
  }
  if (operation === 'comparison') {
    const pair = chooseComparison(user, rng);
    return {
      path: '/api/comparison',
      operation,
      body: { course_a: pair.first, course_b: pair.second },
    };
  }
  if (operation === 'recommendations' || operation === 'next_courses') {
    const includeInactive = rng() < values.inactive_probability;
    const body = {
      selected_courses: [],
      completed_courses: basisIds(user),
      basis: 'completed',
      display_language: language,
      include_inferred: values.include_inferred,
      active_only: !includeInactive,
    };
    if (operation === 'next_courses') {
      body.mode = 'all';
    }
    return {
      path: operation === 'recommendations' ? '/api/recommendations' : '/api/next-courses',
      operation,
      body,
    };
  }
  throw new Error('the workload cycle holds an unknown operation ' + operation);
}

function send(user, request) {
  const response = http.post(baseUrl + request.path, JSON.stringify(request.body), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '180s',
    tags: { user_class: user.className, operation: request.operation },
  });
  const status = String(response.status);
  requestDuration.add(response.timings.duration, {
    user_class: user.className,
    operation: request.operation,
    status,
  });
  if (response.status === 429) {
    refused429.add(1, { user_class: user.className, operation: request.operation });
  }
  if (response.status === 0) {
    transportFailure.add(1, { user_class: user.className, operation: request.operation });
  } else if (response.status !== 200 && response.status !== 429) {
    unexpectedStatus.add(1, { user_class: user.className, operation: request.operation });
  }
  const dateHeader = response.headers.Date || response.headers.date;
  if (!clockRecorded && dateHeader) {
    const serverSeconds = Date.parse(dateHeader) / 1000;
    if (Number.isFinite(serverSeconds)) {
      clockOffset.add(Date.now() / 1000 - serverSeconds);
      clockRecorded = true;
    }
  }
}

function classForUser(profileName, userNumber) {
  if (profileName === 'light_only') {
    return 'light';
  }
  if (profileName !== 'mixed') {
    throw new Error('the workload has no capacity profile ' + profileName);
  }
  const every = workload.capacity.heavy_every;
  if (!Number.isInteger(every) || every < 1) {
    throw new Error('the workload heavy interval must be a positive integer');
  }
  return userNumber % every === 0 ? 'heavy' : 'light';
}

let currentUser = null;

export function defaultIteration(profileName) {
  const userNumber = exec.vu.idInTest;
  const className = classForUser(profileName, userNumber);
  if (
    currentUser === null
    || currentUser.number !== userNumber
    || currentUser.profileName !== profileName
  ) {
    const rng = mulberry32(hash32(workload.seed, userNumber));
    const cycle = workload.cycles[className];
    currentUser = {
      number: userNumber,
      profileName,
      className,
      rng,
      basis: initialBasis(rng, className),
      cursor: (userNumber * 7) % cycle.length,
    };
  }
  const rng = currentUser.rng;
  if (rng() < workload.users.add_probability) {
    addCourse(currentUser, rng);
  }
  if (rng() < workload.users.remove_probability) {
    removeCourse(currentUser, rng);
  }
  const cycle = workload.cycles[currentUser.className];
  const operation = cycle[currentUser.cursor % cycle.length];
  currentUser.cursor += 1;
  send(currentUser, requestFor(operation, currentUser, rng));
  // The pause is the iteration's last draw, so it adds one value to the stream without shifting
  // any request draw.
  sleep(pauseMin + rng() * (pauseMax - pauseMin));
}

function basisFromWorkload(offset, size) {
  return Array.from(
    { length: size },
    (_value, index) => workload.pool[(offset + index) % workload.pool.length],
  );
}

export function warmupRequest(item) {
  const language = workload.display_language;
  if (item.operation === 'search') {
    const groupID = workload.pool[item.query_pool_index % workload.pool.length];
    const course = entry(groupID);
    let text;
    if (item.query === 'code') {
      text = course.code;
    } else if (item.query === 'title') {
      text = course.title_en || course.title_fi;
    } else {
      throw new Error('the warm-up holds an unknown query rule ' + item.query);
    }
    return {
      path: '/api/search',
      body: {
        query: text,
        display_language: language,
        include_inactive: Boolean(item.include_inactive),
      },
    };
  }
  if (item.operation === 'recommendations' || item.operation === 'next_courses') {
    const body = {
      selected_courses: [],
      completed_courses: basisFromWorkload(item.basis_offset, item.basis_size),
      basis: 'completed',
      display_language: language,
      include_inferred: Boolean(item.include_inferred),
      active_only: item.active_only !== false,
    };
    if (item.operation === 'next_courses') {
      body.mode = 'all';
    }
    return {
      path: item.operation === 'recommendations' ? '/api/recommendations' : '/api/next-courses',
      body,
    };
  }
  if (item.operation === 'prerequisites') {
    return {
      path: '/api/prerequisites',
      body: {
        target_code: item.target,
        selected_codes: workload.graph_selected,
        completed_codes: [],
        include_recommended: false,
        include_inferred: Boolean(item.include_inferred),
        active_only: item.active_only === true,
      },
    };
  }
  if (item.operation === 'comparison') {
    return {
      path: '/api/comparison',
      body: {
        course_a: workload.pool[item.course_a_index % workload.pool.length],
        course_b: workload.pool[item.course_b_index % workload.pool.length],
      },
    };
  }
  if (item.operation === 'study_structure') {
    return {
      path: '/api/study-structure',
      body: {
        root_group_ids: payload.study_roots.slice(0, item.root_count || 20),
        allow_unavailable: true,
      },
    };
  }
  if (item.operation === 'catalogue') {
    return { path: '/api/catalogue', body: {} };
  }
  if (item.operation === 'features') {
    return { path: '/api/features', body: {} };
  }
  throw new Error('the warm-up holds an unknown operation ' + item.operation);
}

export function profileSummary(profileName, data) {
  const level = __ENV.LEVEL;
  if (!level) {
    throw new Error('LEVEL is required for the level summary');
  }
  return {
    ['summary-' + profileName + '-' + level + '.json']: JSON.stringify(data),
  };
}

export function buildOptions(profileName) {
  const capacity = workload.capacity;
  if (!capacity.profiles.includes(profileName)) {
    throw new Error('the workload has no capacity profile ' + profileName);
  }
  const level = Number(__ENV.LEVEL);
  if (!Number.isInteger(level) || level < 1) {
    throw new Error('LEVEL must be a positive integer user count');
  }
  if (profileName === 'mixed' && level < capacity.heavy_every) {
    throw new Error('a mixed level needs at least one heavy user');
  }
  return {
    discardResponseBodies: true,
    // The server closes an idle keep-alive connection after its timeout, and a user pause is longer
    // than that, so a reused idle connection fails with EOF.
    noConnectionReuse: true,
    summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
    scenarios: {
      users: {
        executor: 'constant-vus',
        vus: level,
        duration: capacity.level_seconds + 's',
        gracefulStop: '30s',
      },
    },
    thresholds: {
      unexpected_status: ['count==0'],
    },
  };
}
