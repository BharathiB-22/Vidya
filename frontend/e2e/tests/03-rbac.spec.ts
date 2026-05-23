/**
 * H07-14-03 — RBAC / route protection.
 *
 * Admin tests use the default admin storageState.
 * Faculty tests override storageState to faculty.json.
 */

import { test, expect } from '@playwright/test'

// Path relative to frontend/ (where playwright.config.ts lives)
const FACULTY_STATE = 'e2e/.auth/faculty.json'

// ---------------------------------------------------------------------------
// Admin can reach restricted routes
// ---------------------------------------------------------------------------

test.describe('admin access', () => {
  test('admin can access /users', async ({ page }) => {
    await page.goto('/users')
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()
  })

  test('admin can access /settings', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  })

  test('admin can access /programs', async ({ page }) => {
    await page.goto('/programs')
    await expect(page.getByRole('heading', { name: 'Programs' })).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Faculty is blocked from admin-only routes
// ---------------------------------------------------------------------------

test.describe('faculty RBAC restrictions', () => {
  test.use({ storageState: FACULTY_STATE })

  test('faculty cannot access /users — sees unauthorized page', async ({ page }) => {
    await page.goto('/users')
    // AuthGuard renders UnauthorizedPage — look for expected content
    await expect(
      page.getByText(/not authorized|unauthorized|access denied|don't have permission/i),
    ).toBeVisible({ timeout: 10_000 })
    // Must not show the Users table
    await expect(page.getByRole('heading', { name: 'Users' })).not.toBeVisible()
  })

  test('faculty cannot access /settings — sees unauthorized page', async ({ page }) => {
    await page.goto('/settings')
    await expect(
      page.getByText(/not authorized|unauthorized|access denied|don't have permission/i),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('faculty can access /programs', async ({ page }) => {
    await page.goto('/programs')
    await expect(page.getByRole('heading', { name: 'Programs' })).toBeVisible()
  })

  test('faculty dashboard shows faculty role subtitle', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(
      page.getByText('Build courses, set exams, evaluate labs'),
    ).toBeVisible()
  })
})
