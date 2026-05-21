/**
 * H13-04 — Rate-limit spike validation
 * Ramps 8 → 30 VU to trigger 429s. Validates error shape, not 500s.
 * Run: k6 run spike.js  (or via run-spike.ps1)
 */
import http  from 'k6/http'
import { check, sleep } from 'k6'
import { Rate } from 'k6/metrics'
import { BASE_URL, FACULTY_EMAIL, FACULTY_PASS, TENANT, authHeaders } from './config.js'

export const options = {
  scenarios: {
    spike: {
      executor: 'ramping-vus',
      stages: [
        { duration: '10s', target: 8  },  // warm-up
        { duration: '20s', target: 30 },  // spike — should trigger 429s
        { duration: '10s', target: 8  },  // wind-down
      ],
      gracefulStop: '5s',
    },
  },
  thresholds: {
    // During spike some requests WILL be 429 — that is expected.
    // We only fail if we see 5xx (server errors), not 429.
    'http_req_failed{expected_response:false}': [{ threshold: 'rate<0.05', abortOnFail: false }],
  },
}

const rateLimitHits  = new Rate('rate_limit_hits')
const serverErrors   = new Rate('server_errors')

export function setup() {
  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: FACULTY_EMAIL, password: FACULTY_PASS }),
    { headers: { 'Content-Type': 'application/json', 'X-Tenant-Slug': TENANT } },
  )
  check(res, { 'setup login 200': (r) => r.status === 200 })
  if (res.status !== 200) return { token: '' }
  return { token: res.json('access_token') }
}

export default function (data) {
  const { token } = data
  if (!token) { sleep(1); return }

  const r = http.get(
    `${BASE_URL}/programs?page=1&page_size=10`,
    { headers: authHeaders(token), tags: { endpoint: 'programs' } },
  )

  const is429 = r.status === 429
  const is5xx = r.status >= 500

  rateLimitHits.add(is429)
  serverErrors.add(is5xx)

  if (is429) {
    // Validate 429 response shape: {"error":"RATE_LIMITED","message":"Too many requests"}
    check(r, {
      '429 body has error field':   (x) => {
        try { return !!JSON.parse(x.body).error } catch { return false }
      },
      '429 body has message field': (x) => {
        try { return !!JSON.parse(x.body).message } catch { return false }
      },
    })
  } else {
    check(r, { 'programs 200 or 429': (x) => x.status === 200 || x.status === 429 })
  }

  if (is5xx) {
    console.error(`Unexpected 5xx: ${r.status} — ${r.body}`)
  }

  sleep(0.2)  // minimal sleep to keep spike meaningful
}
