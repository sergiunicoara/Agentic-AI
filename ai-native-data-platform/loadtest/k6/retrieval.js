import http from 'k6/http';
import { check, sleep } from 'k6';

// Usage:
//   k6 run -e BASE_URL=http://localhost:8000 -e WORKSPACE_ID=... -e API_KEY=... loadtest/k6/retrieval.js

export const options = {
  scenarios: {
    steady: {
      executor: 'constant-arrival-rate',
      rate: __ENV.RATE ? parseInt(__ENV.RATE, 10) : 30,
      timeUnit: '1s',
      duration: __ENV.DURATION || '2m',
      preAllocatedVUs: __ENV.VUS ? parseInt(__ENV.VUS, 10) : 50,
      maxVUs: __ENV.MAX_VUS ? parseInt(__ENV.MAX_VUS, 10) : 300,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<900', 'p(99)<1500'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const WORKSPACE_ID = __ENV.WORKSPACE_ID || '';
const API_KEY = __ENV.API_KEY || '';
const EMBEDDING_VERSION_OVERRIDE = __ENV.EMBEDDING_VERSION_OVERRIDE || '';
const ADMIN_TOKEN = __ENV.ADMIN_TOKEN || '';

const QUERIES = [
  'What is our PTO policy?',
  'Summarize the incident response process.',
  'How do I rotate API keys?',
  'What does retrieval_budget_ms do?',
  'Explain shard routing and hedging.',
];

export default function () {
  const q = QUERIES[Math.floor(Math.random() * QUERIES.length)];

  const payload = JSON.stringify({
    workspace_id: WORKSPACE_ID,
    query: q,
    top_k: 8,
  });

  const params = {
    headers: {
      'Content-Type': 'application/json',
      'X-Workspace-Id': WORKSPACE_ID,
      'X-API-Key': API_KEY,
      ...(EMBEDDING_VERSION_OVERRIDE ? { 'X-Embedding-Version-Override': EMBEDDING_VERSION_OVERRIDE } : {}),
      ...(ADMIN_TOKEN ? { 'X-Admin-Token': ADMIN_TOKEN } : {}),
    },
    timeout: '5s',
  };

  const res = http.post(`${BASE_URL}/ask`, payload, params);
  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  sleep(0.05);
}
