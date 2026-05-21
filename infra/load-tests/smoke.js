/**
 * H13-02 — Smoke baseline
 * 1 VU, 30 s, covers health + auth + key read-only endpoints.
 * Run: k6 run smoke.js  (or via run-smoke.ps1)
 */
import http  from 'k6/http'
import { check, sleep } from 'k6'
import { Rate, Trend } from 'k6/metrics'
import { BASE_URL, FACULTY_EMAIL, FACULTY_PASS, TENANT, authHeaders, SMOKE_THRESHOLDS } from './config.js'

export const options = {
  vus:      1,
  duration: '30s',
  tags:     { phase: 'smoke' },
  thresholds: SMOKE_THRESHOLDS,
}

const loginErrors = new Rate('login_errors')
const authTrend   = new Trend('auth_login_duration', true)

// ── one-time setup: obtain token ─────────────────────────────────────────────
export function setup() {
  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ email: FACULTY_EMAIL, password: FACULTY_PASS }),
    { headers: { 'Content-Type': 'application/json', 'X-Tenant-Slug': TENANT } },
  )
  authTrend.add(res.timings.duration)
  loginErrors.add(res.status !== 200)

  check(res, { 'login 200': (r) => r.status === 200 })
  if (res.status !== 200) {
    console.error(`Login failed: ${res.status} — ${res.body}`)
    return { token: '' }
  }
  return { token: res.json('access_token') }
}

// ── per-VU iteration ─────────────────────────────────────────────────────────
export default function (data) {
  const { token } = data
  if (!token) { sleep(1); return }

  const H = authHeaders(token)

  // Health probes (no auth needed)
  let r = http.get(`${BASE_URL.replace('/api', '')}/healthz`)
  check(r, { 'healthz 200': (x) => x.status === 200 })

  r = http.get(`${BASE_URL.replace('/api', '')}/ready`)
  check(r, { 'ready 200': (x) => x.status === 200 })

  // Auth endpoint
  r = http.get(`${BASE_URL}/auth/me`, { headers: H })
  check(r, { 'auth/me 200': (x) => x.status === 200 })

  // Programs list (read-only, FACULTY visible)
  r = http.get(`${BASE_URL}/programs?page=1&page_size=10`, { headers: H })
  check(r, { 'programs 200': (x) => x.status === 200 })

  // Notifications list
  r = http.get(`${BASE_URL}/notifications?page=1&page_size=10`, { headers: H })
  check(r, { 'notifications 200': (x) => x.status === 200 })

  sleep(1)
}
