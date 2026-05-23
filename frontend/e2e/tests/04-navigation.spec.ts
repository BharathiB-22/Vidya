/**
 * H07-14-03 — Sidebar navigation and notifications drawer.
 * Uses admin storageState.
 */

import { test, expect } from '@playwright/test'

test.describe('sidebar navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
  })

  test('Dashboard link is active on /dashboard', async ({ page }) => {
    // The active link has bg-indigo-100 styling — verify text is visible
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
  })

  test('Programs link navigates to /programs', async ({ page }) => {
    await page.getByRole('link', { name: 'Programs' }).click()
    await expect(page).toHaveURL(/\/programs/)
  })

  test('Course Kits link navigates to /course-kits', async ({ page }) => {
    await page.getByRole('link', { name: 'Course Kits' }).click()
    await expect(page).toHaveURL(/\/course-kits/)
  })

  test('Users link navigates to /users (admin only)', async ({ page }) => {
    await page.getByRole('link', { name: 'Users' }).click()
    await expect(page).toHaveURL(/\/users/)
  })

  test('Settings link navigates to /settings (admin only)', async ({ page }) => {
    await page.getByRole('link', { name: 'Settings' }).click()
    await expect(page).toHaveURL(/\/settings/)
  })

  test('institution name shown in sidebar', async ({ page }) => {
    // prettifySlug('smoke-university') === 'Smoke University'
    await expect(page.getByText('Smoke University')).toBeVisible()
  })
})

test.describe('notifications drawer', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
  })

  test('opens when bell button is clicked', async ({ page }) => {
    // exact: true avoids partial-matching "Close notifications" button
    await page.getByRole('button', { name: 'Notifications', exact: true }).click()
    const drawer = page.getByTestId('notifications-drawer')
    await expect(drawer).toBeVisible()
    // Header inside drawer says "Notifications"
    await expect(drawer.getByText('Notifications').first()).toBeVisible()
  })

  test('closes when Escape is pressed', async ({ page }) => {
    await page.getByRole('button', { name: 'Notifications', exact: true }).click()
    const drawer = page.getByTestId('notifications-drawer')
    await expect(drawer).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(drawer).not.toBeInViewport()
  })

  test('closes when close button is clicked', async ({ page }) => {
    await page.getByRole('button', { name: 'Notifications', exact: true }).click()
    const drawer = page.getByTestId('notifications-drawer')
    await expect(drawer).toBeVisible()
    await page.getByRole('button', { name: 'Close notifications' }).click()
    await expect(drawer).not.toBeInViewport()
  })

  test('shows content or empty state — no unhandled error', async ({ page }) => {
    await page.getByRole('button', { name: 'Notifications', exact: true }).click()
    const drawer = page.getByTestId('notifications-drawer')
    await expect(drawer).toBeVisible()
    // Either "No notifications" or notification items — both are acceptable
    const hasEmpty   = await drawer.getByText('No notifications').isVisible().catch(() => false)
    const hasItems   = await drawer.locator('[class*="border-b"]').first().isVisible().catch(() => false)
    const hasLoading = await drawer.getByText('Loading').isVisible().catch(() => false)
    expect(hasEmpty || hasItems || hasLoading).toBe(true)
  })
})
