import http from 'k6/http';
import { check, sleep } from 'k6';

// Usage:
//   k6 run -e BASE_URL=http://localhost:8000 -e WORKSPACE_ID=... -e API_KEY=... -e RATE=5 -e DURATION=5m loadtest/k6/ingest.js

export const options = {
  scenarios: {
    ingest: {
      executor: 'constant-arrival-rate',
      rate: __ENV.RATE ? parseInt(__ENV.RATE, 10) : 5,
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: __ENV.VUS ? parseInt(__ENV.VUS, 10) : 20,
      maxVUs: __ENV.MAX_VUS ? parseInt(__ENV.MAX_VUS, 10) : 120,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<800', 'p(99)<1200'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const WORKSPACE_ID = __ENV.WORKSPACE_ID || '';
const API_KEY = __ENV.API_KEY || '';

function randStr(len) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  for (let i = 0; i < len; i++) out += chars[Math.floor(Math.random() * chars.length)];
  return out;
}

export default function () {
  const external = `loadtest-${randStr(10)}`;

  const payload = JSON.stringify({
    workspace_id: WORKSPACE_ID,
    source: 'loadtest',
    external_id: external,
    title: `Loadtest ${external}`,
    text: `This is a synthetic document for ingestion load testing. Token ${randStr(16)}.\n\n` +
          `It exists only to exercise throughput, batching, and indexing backpressure.`,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'X-Workspace-Id': WORKSPACE_ID,
      'X-API-Key': API_KEY,
    },
    timeout: '5s',
  };

  const res = http.post(`${BASE_URL}/ingest/transcript`, payload, params);
  check(res, {
    'status 200/queued': (r) => r.status === 200,
  });

  sleep(0.05);
}
