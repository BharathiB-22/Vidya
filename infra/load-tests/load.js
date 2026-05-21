/**
 * H13-03 — Sustained load baseline
 * 10 VU × 60 s, read-only endpoints, sleep(1) per iteration (~10 req/s peak).
 * Run: k6 run load.js  (or via run-load.ps1)
 */
import http  from 'k6/http'
import { check, sleep } from 'k6'
import { BASE_URL, FACULTY_EMAIL, FACULTY_PASS, TENANT, authHeaders, LOAD_THRESHOLDS } from './config.js'

export const options = {
  scenarios: {
    sustained: {
      executor:          'constant-vus',
      vus:               10,
      duration:          '60s',
      gracefulStop:      '10s',
    },
  },
  thresholds: LOAD_THRESHOLDS,
}

// ── one-time setup: obtain token ─────────────────────────────────────────────
export function setup() {
  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: FACULTY_EMAIL, password: FACULTY_PASS }),
    { headers: { 'Content-Type': 'application/json', 'X-Tenant-Slug': TENANT } },
  )
  check(res, { 'setup login 200': (r) => r.status === 200 })
  if (res.status !== 200) {
    console.error(`Setup login failed: ${res.status} — ${res.body}`)
    return { token: '' }
  }
  return { token: res.json('access_token') }
}

// ── per-VU iteration ─────────────────────────────────────────────────────────
export default function (data) {
  const { token } = data
  if (!token) { sleep(1); return }

  const H = authHeaders(token)

  // Round-robin across safe read-only endpoints
  const vu = __VU % 3

  if (vu === 0) {
    const r = http.get(`${BASE_URL}/programs?page=1&page_size=10`, { headers: H, tags: { endpoint: 'programs' } })
    check(r, { 'programs 200': (x) => x.status === 200 })
  } else if (vu === 1) {
    const r = http.get(`${BASE_URL}/notifications?page=1&page_size=10`, { headers: H, tags: { endpoint: 'notifications' } })
    check(r, { 'notifications 200': (x) => x.status === 200 })
  } else {
    const r = http.get(`${BASE_URL}/auth/me`, { headers: H, tags: { endpoint: 'auth_me' } })
    check(r, { 'auth/me 200': (x) => x.status === 200 })
  }

  sleep(1)
}
