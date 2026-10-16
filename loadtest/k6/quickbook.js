// QuickBook user journey for k6 (open model: users arrive at a set rate whatever the response times).
// PROFILE=gate   -> 30 s warm-up (not scored) + 90 s at 1.5 users/s with SLO thresholds (CI gate; exit 99 on breach)
// PROFILE=stress -> 1 -> 2 -> 4 -> 6 -> 8 -> 10 users/s, 60 s each (same ramp as scripts/load_profiles/stress-ramp.json)
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://frontend.quickbook.svc.cluster.local';
const PROFILE = __ENV.PROFILE || 'gate';
const SCALE = Number(__ENV.TIME_SCALE || '0.25'); // shrink think times, like the Python profiles

const step = (rate) => [{ target: rate, duration: '0s' }, { target: rate, duration: '60s' }];
const SCENARIOS = {
  // Warm-up first: the gate runs seconds after a rollout, and brand-new pods are cold (first imports,
  // DB connections, DNS). Only the "gate" scenario is scored, so cold starts don't fail a good release.
  warmup: { executor: 'constant-arrival-rate', rate: 15, timeUnit: '10s', duration: '30s', preAllocatedVUs: 40, maxVUs: 300 },
  gate: { executor: 'constant-arrival-rate', rate: 15, timeUnit: '10s', duration: '90s', startTime: '30s',
          preAllocatedVUs: 40, maxVUs: 300 },
  stress: { executor: 'ramping-arrival-rate', startRate: 1, timeUnit: '1s', preAllocatedVUs: 100, maxVUs: 800,
            stages: [1, 2, 4, 6, 8, 10].flatMap(step) },
};

// SLOs (same as scripts/load_profiles/load-steady.json), scored on the "gate" scenario only.
const SLO = {
  'http_req_failed{scenario:gate}': ['rate<0.01'],
  'http_req_duration{scenario:gate,step:signin}': ['p(95)<2500'],
  'http_req_duration{scenario:gate,step:signup}': ['p(95)<2500'],
  'http_req_duration{scenario:gate,step:search}': ['p(95)<500'],
  'http_req_duration{scenario:gate,step:create_booking}': ['p(95)<500'],
  'http_req_duration{scenario:gate,step:payment}': ['p(95)<500'],
  'http_req_duration{scenario:gate,step:ticket_pdf}': ['p(95)<500'],
};

export const options = {
  scenarios: PROFILE === 'gate' ? { warmup: SCENARIOS.warmup, gate: SCENARIOS.gate } : { users: SCENARIOS[PROFILE] },
  thresholds: PROFILE === 'gate' ? SLO : {},
  summaryTrendStats: ['p(50)', 'p(95)', 'p(99)', 'max'],
};

// 402 = the deliberately declined test card: expected, not a failure.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 399 }, 402));

const CITIES = ['Delhi', 'Mumbai', 'Bengaluru', 'Chennai', 'Kolkata', 'Hyderabad'];
const lognormal = (median, sigma) => {
  const u = 1 - Math.random(), v = Math.random();
  return median * Math.exp(sigma * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v));
};
const think = (median, sigma) => sleep(lognormal(median, sigma) * SCALE);
// Every request gets the gateway's 30 s timeout, so a stuck request can't hold the test open.
const TIMEOUT = '30s';
const json = { headers: { 'Content-Type': 'application/json' }, timeout: TIMEOUT };
const auth = (t) => ({ headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${t}` }, timeout: TIMEOUT });
const pick = (a) => a[Math.floor(Math.random() * a.length)];

export function setup() {  // returning users, created before measuring
  const pool = [];
  for (let i = 0; i < 40; i++) {
    const acc = { full_name: `Returning User ${i}`, email: `k6.returning.${Date.now()}.${i}@example.com`, password: 'loadtest-123' };
    if (http.post(`${BASE}/api/auth/signup`, JSON.stringify(acc), json).status === 201) pool.push(acc);
  }
  return { pool };
}

export default function (data) {
  http.get(`${BASE}/`, { tags: { step: 'home' }, timeout: TIMEOUT });
  let res;
  if (Math.random() < 0.3 || data.pool.length === 0) {
    think(20, 0.5);
    const acc = { full_name: 'K6 User', email: `k6.${__VU}.${__ITER}.${Date.now()}@example.com`, password: 'loadtest-123' };
    res = http.post(`${BASE}/api/auth/signup`, JSON.stringify(acc), { ...json, tags: { step: 'signup' } });
  } else {
    think(6, 0.4);
    const acc = pick(data.pool);
    res = http.post(`${BASE}/api/auth/signin`, JSON.stringify({ email: acc.email, password: acc.password }),
                    { ...json, tags: { step: 'signin' } });
  }
  if (!check(res, { 'logged in': (r) => r.status === 200 || r.status === 201 })) return;
  const token = res.json('access_token');

  const mode = Math.random() < 0.55 ? 'flight' : 'train';
  let trips = [], date;
  for (let i = 0, n = 1 + Math.floor(Math.random() * 3); i < n; i++) {
    think(8, 0.6);
    let [from, to] = [pick(CITIES), pick(CITIES)];
    while (to === from) to = pick(CITIES);
    date = new Date(Date.now() + (1 + Math.floor(Math.random() * 60)) * 864e5).toISOString().slice(0, 10);
    const r = http.get(`${BASE}/api/inventory/search?mode=${mode}&origin=${from}&destination=${to}&date=${date}`,
                       { tags: { step: 'search' }, timeout: TIMEOUT });
    if (r.status !== 200) return;
    trips = r.json();
  }
  if (!trips.length || Math.random() > 0.8) return;

  think(25, 0.5);
  const trip = pick(trips);
  const passengers = Array.from({ length: 1 + Math.floor(Math.random() * 4) }, (_, i) => ({ name: `Passenger ${i + 1}`, age: 30 }));
  const b = http.post(`${BASE}/api/bookings`, JSON.stringify({ schedule_id: trip.schedule_id, travel_date: date, passengers }),
                      { ...auth(token), tags: { step: 'create_booking' } });
  if (b.status !== 201) return;
  const booking = b.json();

  think(15, 0.4);
  const card = { booking_id: booking.id, card_holder: 'K6 User', expiry: '12/29', cvv: '123' };
  if (Math.random() < 0.1) {
    http.post(`${BASE}/api/payments`, JSON.stringify({ ...card, card_number: '4000000000000002' }),
              { ...auth(token), tags: { step: 'payment_declined' } });
    if (Math.random() < 0.4) return;
    think(15, 0.4);
  }
  const p = http.post(`${BASE}/api/payments`, JSON.stringify({ ...card, card_number: '4111111111111111' }),
                      { ...auth(token), tags: { step: 'payment' } });
  if (p.status !== 201) return;
  if (Math.random() < 0.9) {
    think(5, 1.0);
    http.get(`${BASE}/api/tickets/${booking.id}`, { ...auth(token), tags: { step: 'ticket_pdf' } });
  }
}
