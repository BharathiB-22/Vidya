/**
 * Auth setup — runs once before all test projects.
 * Uses the Vite /api proxy to authenticate against the backend,
 * then saves browser storage state so tests start pre-authenticated.
 *
 * Prerequisites:
 *   1. `npm run dev` running in frontend/ (or server already up at PLAYWRIGHT_BASE_URL)
 *   2. Backend accessible at localhost:8000  (e.g. kubectl port-forward svc/vidya-api 8000:8000 -n vidya-system)
 */

import { test as setup } from '@playwright/test'
import { mkdirSync } from 'fs'
import {
  TENANT, ADMIN_EMAIL, ADMIN_PASS, FACULTY_EMAIL, FACULTY_PASS,
} from './support/credentials'

// Paths are relative to the directory where `npx playwright test` is run (frontend/).
const AUTH_DIR     = 'e2e/.auth'
const ADMIN_FILE   = 'e2e/.auth/admin.json'
const FACULTY_FILE = 'e2e/.auth/faculty.json'

mkdirSync(AUTH_DIR, { recursive: true })

/** Authenticate via the Vite /api proxy and save localStorage state. */
async function saveSession(
  page: import('@playwright/test').Page,
  email: string,
  password: string,
  outFile: string,
) {
  // Navigate to the app origin so fetch() calls go through the Vite proxy.
  await page.goto('/login')

  // POST /api/auth/login through Vite proxy (→ localhost:8000/auth/login)
  const tokens = await page.evaluate(
    async ({ e, p, slug }) => {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Tenant-Slug': slug },
        body: JSON.stringify({ email: e, password: p }),
      })
      if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`)
      return res.json() as Promise<{ access_token: string; refresh_token?: string }>
    },
    { e: email, p: password, slug: TENANT },
  )

  // GET /api/auth/me to retrieve the role
  const me = await page.evaluate(
    async ({ token, slug }) => {
      const res = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant-Slug': slug },
      })
      if (!res.ok) throw new Error(`/auth/me failed: ${res.status}`)
      return res.json() as Promise<{ role: string; first_login: boolean }>
    },
    { token: tokens.access_token, slug: TENANT },
  )

  // Seed localStorage so the React app sees an authenticated session.
  await page.evaluate(
    ({ token, refresh, slug, role }) => {
      localStorage.setItem('vidya_token',        token)
      localStorage.setItem('vidya_tenant_slug',  slug)
      localStorage.setItem('vidya_role',         role)
      if (refresh) localStorage.setItem('vidya_refresh_token', refresh)
    },
    {
      token:   tokens.access_token,
      refresh: tokens.refresh_token ?? '',
      slug:    TENANT,
      role:    me.role,
    },
  )

  await page.context().storageState({ path: outFile })
}

setup('save admin session', async ({ page }) => {
  await saveSession(page, ADMIN_EMAIL, ADMIN_PASS, ADMIN_FILE)
})

setup('save faculty session', async ({ page }) => {
  await saveSession(page, FACULTY_EMAIL, FACULTY_PASS, FACULTY_FILE)
})
