/**
 * H07-14-05 — Mobile viewport smoke checks.
 * Uses Pixel 5 viewport from the mobile-chrome project.
 * Uses admin storageState.
 */

import { test, expect } from '@playwright/test'

test.describe('mobile — login page', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('login form is usable on mobile viewport', async ({ page }) => {
    await page.goto('/login')
    await expect(page.locator('#slug')).toBeVisible()
    await expect(page.locator('#email')).toBeVisible()
    await expect(page.locator('#password')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible()
    // No horizontal scroll
    const bodyWidth  = await page.evaluate(() => document.body.scrollWidth)
    const innerWidth = await page.evaluate(() => window.innerWidth)
    expect(bodyWidth).toBeLessThanOrEqual(innerWidth + 2)
  })
})

test.describe('mobile — authenticated app shell', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
  })

  test('sidebar is hidden by default on mobile', async ({ page }) => {
    // On mobile the sidebar starts off-screen (translate-x-full)
    const aside = page.locator('aside')
    const box   = await aside.boundingBox()
    // The aside either has negative x (off-screen) or isn't in the viewport
    if (box) {
      expect(box.x + box.width).toBeLessThanOrEqual(0)
    } else {
      // Not in viewport — acceptable
      expect(true).toBe(true)
    }
  })

  test('hamburger button opens sidebar on mobile', async ({ page }) => {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    // Sidebar slides in — "Vidya" brand is now visible
    await expect(page.getByText('Vidya').first()).toBeVisible()
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
  })

  test('close button hides sidebar on mobile', async ({ page }) => {
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    // Close sidebar
    await page.getByRole('button', { name: 'Close sidebar' }).click()
    // Sidebar slides back off-screen
    const aside = page.locator('aside')
    await expect(aside).not.toBeInViewport()
  })

  test('notifications drawer opens on mobile', async ({ page }) => {
    await page.getByRole('button', { name: 'Notifications', exact: true }).click()
    await expect(page.getByTestId('notifications-drawer')).toBeVisible()
  })

  test('dashboard module cards are visible on mobile', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Programs/ })).toBeVisible()
  })

  test('no horizontal overflow on dashboard', async ({ page }) => {
    const bodyWidth  = await page.evaluate(() => document.body.scrollWidth)
    const innerWidth = await page.evaluate(() => window.innerWidth)
    expect(bodyWidth).toBeLessThanOrEqual(innerWidth + 2)
  })
})
