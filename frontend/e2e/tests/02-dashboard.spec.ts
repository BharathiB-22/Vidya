/**
 * H07-14-02 — Dashboard rendering (admin role).
 * Uses admin storageState from global setup.
 */

import { test, expect } from '@playwright/test'

test.describe('dashboard page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
  })

  test('renders time-of-day greeting', async ({ page }) => {
    await expect(page.getByText(/Good (morning|afternoon|evening)/)).toBeVisible()
  })

  test('shows admin role subtitle', async ({ page }) => {
    await expect(
      page.getByText('Manage programs, users, and platform settings'),
    ).toBeVisible()
  })

  test('shows onboarding checklist widget', async ({ page }) => {
    // Widget is visible for admin — either "Getting started" or "Setup complete"
    await expect(page.getByTestId('onboarding-checklist')).toBeVisible()
  })

  test('shows admin module cards', async ({ page }) => {
    await expect(page.getByRole('button', { name: /Programs/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Course Kits/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /Lab Assignments/ })).toBeVisible()
  })

  test('Programs card navigates to /programs', async ({ page }) => {
    await page.getByRole('button', { name: /Programs/ }).click()
    await expect(page).toHaveURL(/\/programs/)
  })

  test('Course Kits card navigates to /course-kits', async ({ page }) => {
    await page.goto('/dashboard')
    await page.getByRole('button', { name: /Course Kits/ }).click()
    await expect(page).toHaveURL(/\/course-kits/)
  })
})
