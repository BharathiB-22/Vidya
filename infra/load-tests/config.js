/**
 * Shared configuration for all Vidya k6 load tests.
 *
 * Override defaults via environment variables:
 *   k6 run -e BASE_URL=http://... -e TENANT=... -e FACULTY_EMAIL=... -e FACULTY_PASSWORD=... smoke.js
 */

export const BASE_URL      = __ENV.BASE_URL       || 'http://vidya.127.0.0.1.nip.io:9080/api'
export const TENANT        = __ENV.TENANT         || 'dev'
export const FACULTY_EMAIL = __ENV.FACULTY_EMAIL  || 'faculty@dev.vidya.local'
export const FACULTY_PASS  = __ENV.FACULTY_PASS   || 'Faculty@123'
export const ADMIN_EMAIL   = __ENV.ADMIN_EMAIL    || 'admin@dev.vidya.local'
export const ADMIN_PASS    = __ENV.ADMIN_PASS     || 'Admin@123'

/** Standard JSON auth headers — pass token obtained in setup() */
export function authHeaders(token) {
  return {
    'Content-Type':  'application/json',
    'X-Tenant-Slug': TENANT,
    'Authorization': `Bearer ${token}`,
  }
}

/** Thresholds shared across smoke and load tests */
export const SMOKE_THRESHOLDS = {
  http_req_failed:   [{ threshold: 'rate<0.01',  abortOnFail: true }],   // <1 % errors
  http_req_duration: [{ threshold: 'p(95)<500',  abortOnFail: false }],  // p95 < 500 ms
                                                                          // p99 < 1 000 ms
  'http_req_duration{phase:smoke}': [{ threshold: 'p(99)<1000', abortOnFail: false }],
}

export const LOAD_THRESHOLDS = {
  http_req_failed:   [{ threshold: 'rate<0.01',  abortOnFail: true  }],  // <1 % errors
  http_req_duration: [
    { threshold: 'p(50)<200',  abortOnFail: false },
    { threshold: 'p(95)<800',  abortOnFail: false },
    { threshold: 'p(99)<1500', abortOnFail: false },
  ],
}
