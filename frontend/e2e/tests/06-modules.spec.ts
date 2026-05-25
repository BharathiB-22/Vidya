/**
 * H07-14-04 — Module list page smoke tests (M01 / M02 / M03 happy path).
 * Uses admin storageState. Tests verify pages load and display expected chrome.
 * AI generation is NOT triggered — these are list-page smoke checks only.
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// M01 — Programs
// ---------------------------------------------------------------------------

test.describe('Programs (M01)', () => {
  test('list page loads with heading and filter bar', async ({ page }) => {
    await page.goto('/programs')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Programs' })).toBeVisible()
    // Status filter pills
    await expect(page.getByRole('button', { name: 'All' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Draft' })).toBeVisible()
  })

  test('New Program button is visible for admin', async ({ page }) => {
    await page.goto('/programs')
    await expect(page.getByRole('button', { name: /New Program/ })).toBeVisible()
  })

  test('New Program button opens create dialog', async ({ page }) => {
    await page.goto('/programs')
    await page.getByRole('button', { name: /New Program/ }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('status filter updates selection state', async ({ page }) => {
    await page.goto('/programs')
    await page.waitForLoadState('networkidle')
    const draftBtn = page.getByRole('button', { name: 'Draft' })
    await draftBtn.click()
    // After clicking Draft, it should have active styling (bg-blue-600 text)
    await expect(draftBtn).toHaveClass(/bg-blue-600/)
  })
})

// ---------------------------------------------------------------------------
// M02 — Syllabuses
// ---------------------------------------------------------------------------

test.describe('Syllabuses (M02)', () => {
  test('list page loads', async ({ page }) => {
    await page.goto('/syllabuses')
    await page.waitForLoadState('networkidle')
    // Page should not show an error; either a list or an empty state
    await expect(page.locator('body')).not.toContainText('500')
    await expect(page.locator('body')).not.toContainText('Unhandled Error')
  })

  test('page contains syllabuses heading or empty state', async ({ page }) => {
    await page.goto('/syllabuses')
    await page.waitForLoadState('networkidle')
    const hasHeading  = await page.getByRole('heading', { name: /Syllabuses?/i }).isVisible().catch(() => false)
    const hasEmpty    = await page.getByText(/No syllabuses/i).isVisible().catch(() => false)
    const hasLoading  = await page.getByText(/Loading/i).isVisible().catch(() => false)
    // /syllabuses requires ?course_id= — without it the page shows a prompt
    const hasPrompt   = await page.getByText(/course_id/i).isVisible().catch(() => false)
    expect(hasHeading || hasEmpty || hasLoading || hasPrompt).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// M03 — Course Kits
// ---------------------------------------------------------------------------

test.describe('Course Kits (M03)', () => {
  test('list page loads', async ({ page }) => {
    await page.goto('/course-kits')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).not.toContainText('500')
    await expect(page.locator('body')).not.toContainText('Unhandled Error')
  })

  test('page contains course kits heading or empty state', async ({ page }) => {
    await page.goto('/course-kits')
    await page.waitForLoadState('networkidle')
    const hasHeading  = await page.getByRole('heading', { name: /Course Kits?/i }).isVisible().catch(() => false)
    const hasEmpty    = await page.getByText(/No course kits/i).isVisible().catch(() => false)
    const hasLoading  = await page.getByText(/Loading/i).isVisible().catch(() => false)
    // /course-kits requires ?syllabus_id= — without it the page shows a prompt
    const hasPrompt   = await page.getByText(/syllabus_id/i).isVisible().catch(() => false)
    expect(hasHeading || hasEmpty || hasLoading || hasPrompt).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// Settings page (admin account management)
// ---------------------------------------------------------------------------

test.describe('Settings page', () => {
  test('loads and shows institution and account sections', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Institution' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Your account' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Change password' })).toBeVisible()
  })

  test('shows correct tenant slug', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByText('smoke-university')).toBeVisible()
  })

  test('password mismatch shows validation error', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    const section = page.locator('section').filter({ hasText: 'Change password' })
    // Labels use no htmlFor — target inputs by type+order within the form
    const pwInputs = section.locator('input[type="password"]')
    await pwInputs.nth(0).fill('SomePass1!')
    await pwInputs.nth(1).fill('NewPass@1')
    await pwInputs.nth(2).fill('DifferentPass@1')
    await section.getByRole('button', { name: 'Change password' }).click()
    await expect(section.getByText('New passwords do not match')).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// M07 — Student Research Proposal Detail page
// ---------------------------------------------------------------------------

test.describe('Student Research Detail (M07)', () => {
  test('navigating to a non-existent proposal shows error state, not blank screen', async ({ page }) => {
    // Use a valid-format UUID that won't exist in the DB
    await page.goto('/student/research/00000000-0000-0000-0000-000000000000')
    await page.waitForLoadState('networkidle')

    // Must not be a blank white screen — the body should have visible content
    const bodyText = await page.locator('body').innerText()
    expect(bodyText.trim().length).toBeGreaterThan(0)

    // Should show error state or redirect, never a 500 or unhandled exception
    await expect(page.locator('body')).not.toContainText('Unhandled Error')
    await expect(page.locator('body')).not.toContainText('Cannot read properties')

    // Either the error card or a redirect to login/research list is acceptable
    const hasErrorCard  = await page.getByText(/not found|failed to load|access denied/i).isVisible().catch(() => false)
    const hasBackButton = await page.getByRole('button', { name: /back|my research/i }).isVisible().catch(() => false)
    const onListPage    = page.url().includes('/student/research') && !page.url().includes('/00000000')
    expect(hasErrorCard || hasBackButton || onListPage).toBe(true)
  })

  test('My Research list page loads without blank screen', async ({ page }) => {
    await page.goto('/student/research')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('body')).not.toContainText('Unhandled Error')
    const hasHeading = await page.getByRole('heading', { name: /My Research/i }).isVisible().catch(() => false)
    const hasEmpty   = await page.getByText(/No proposals/i).isVisible().catch(() => false)
    const hasLoading = await page.locator('[class*="animate-spin"]').isVisible().catch(() => false)
    expect(hasHeading || hasEmpty || hasLoading).toBe(true)
  })
})
