/**
 * H07-14-03 — Admin user management.
 * Uses admin storageState.
 */

import { test, expect } from '@playwright/test'

test.describe('users page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/users')
    await page.waitForLoadState('networkidle')
  })

  test('renders Users heading and user count', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Users' })).toBeVisible()
    // Sub-heading shows "N user(s) in this institution"
    await expect(page.getByText(/user.* in this institution/)).toBeVisible()
  })

  test('shows users table with columns', async ({ page }) => {
    await expect(page.getByRole('columnheader', { name: 'Name' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Email' })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: 'Role' })).toBeVisible()
  })

  test('Add user button opens create dialog', async ({ page }) => {
    await page.getByRole('button', { name: 'Add user' }).click()
    // Dialog title appears
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Add user' })).toBeVisible()
  })

  test('create user dialog validates required fields', async ({ page }) => {
    await page.getByRole('button', { name: 'Add user' }).click()
    await page.getByRole('button', { name: 'Create user' }).click()
    // Browser or custom validation fires — dialog stays open
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('admin can create a new user', async ({ page }) => {
    const ts    = Date.now()
    const email = `e2e-user-${ts}@smoke-uni.edu`
    const name  = `E2E User ${ts}`

    await page.getByRole('button', { name: 'Add user' }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    await dialog.getByLabel('Full name').fill(name)
    await dialog.getByLabel('Email').fill(email)
    await dialog.getByLabel('Temporary password').fill('Test@Pass1')
    // Role defaults to FACULTY — leave as-is

    await dialog.getByRole('button', { name: 'Create user' }).click()

    // Dialog closes and new user appears in the table
    await expect(dialog).not.toBeVisible({ timeout: 10_000 })
    await expect(page.getByRole('cell', { name })).toBeVisible()
    await expect(page.getByRole('cell', { name: email })).toBeVisible()
  })

  test('search filters user list', async ({ page }) => {
    const searchInput = page.getByPlaceholder('Search name, email, ID…')
    await searchInput.fill('nonexistentzzzz')
    // Either shows "No users match your filter." or no matching rows
    const noMatch = await page.getByText('No users match your filter.').isVisible().catch(() => false)
    const hasRows = await page.locator('tbody tr').count()
    // With a nonsense query, either no-match message shows or zero rows remain
    expect(noMatch || hasRows === 1).toBe(true) // 1 = the "no match" empty row
  })
})
