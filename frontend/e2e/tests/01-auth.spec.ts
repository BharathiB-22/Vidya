/**
 * H07-14-02 — Login / logout flows.
 * Some tests override storageState to run without a pre-authenticated session.
 */

import { test, expect } from '@playwright/test'
import { TENANT, ADMIN_EMAIL, ADMIN_PASS } from '../support/credentials'

// ---------------------------------------------------------------------------
// Unauthenticated tests — no stored session
// ---------------------------------------------------------------------------

test.describe('login page', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('renders login form with all fields', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('#slug')).toBeVisible()
    await expect(page.locator('#email')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
  })

  test('shows error on wrong password', async ({ page }) => {
    await page.goto('/login')
    await page.fill('#slug', TENANT)
    await page.fill('#email', ADMIN_EMAIL)
    await page.fill('#password', 'WrongPass!99')
    await page.click('button[type="submit"]')
    // Error message appears in the red banner — any non-empty message is fine
    await expect(page.locator('p.text-red-600')).toBeVisible()
    // URL stays on /login
    await expect(page).toHaveURL(/\/login/)
  })

  test('shows error on unknown tenant slug', async ({ page }) => {
    await page.goto('/login')
    await page.fill('#slug', 'does-not-exist-tenant')
    await page.fill('#email', 'nobody@example.com')
    await page.fill('#password', 'SomePass1!')
    await page.click('button[type="submit"]')
    await expect(page.locator('p.text-red-600')).toBeVisible()
  })

  test('unauthenticated /dashboard redirects to /login', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page).toHaveURL(/\/login/)
  })

  test('unauthenticated /programs redirects to /login', async ({ page }) => {
    await page.goto('/programs')
    await expect(page).toHaveURL(/\/login/)
  })

  test('successful login navigates to dashboard', async ({ page }) => {
    // Mock to avoid rate-limit: auth-setup (2) + wrong-pw + wrong-slug = 4 calls/min already used
    await page.route('**/api/auth/login', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: 'e2e_mock', refresh_token: 'e2e_refresh', token_type: 'bearer', expires_in: 3600 }),
    }))
    await page.route('**/api/auth/me', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'mock-id', email: ADMIN_EMAIL, full_name: 'Test Admin', role: 'ADMIN', first_login: false, schema_name: 'tenant_smoke_university' }),
    }))

    await page.goto('/login')
    await page.fill('#slug', TENANT)
    await page.fill('#email', ADMIN_EMAIL)
    await page.fill('#password', ADMIN_PASS)
    await page.click('button[type="submit"]')
    // Accept dashboard or first-login — either is correct behaviour
    await page.waitForURL(/\/(dashboard|first-login)/, { timeout: 15_000 })
    await expect(page).toHaveURL(/\/(dashboard|first-login)/)
  })
})

// ---------------------------------------------------------------------------
// Authenticated tests — use default admin storageState
// ---------------------------------------------------------------------------

test.describe('logout', () => {
  test('signs out and redirects to login page', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')

    // Open user menu
    await page.getByTestId('user-menu-trigger').click()
    await expect(page.getByTestId('signout-btn')).toBeVisible()

    // Click sign out
    await page.getByTestId('signout-btn').click()

    // Should land on login page
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 })
    await expect(page.locator('#email')).toBeVisible()
  })
})
