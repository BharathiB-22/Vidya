import { defineConfig, devices } from '@playwright/test'

// Default: Vite dev server with API port-forwarded to localhost:8000.
//   1. Start: kubectl port-forward svc/vidya-api 8000:8000 -n vidya-system
//   2. Start: cd frontend && npm run dev
//   3. Run:   npx playwright test  (from frontend/)
//
// KIND ingress alternative (requires ingress port-forward instead):
//   PLAYWRIGHT_BASE_URL=http://vidya.127.0.0.1.nip.io:8088 npx playwright test
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['line'],
  ],

  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },

  projects: [
    // Auth setup — runs first, saves storageState for admin and faculty
    {
      name: 'setup',
      testMatch: ['**/auth.setup.ts'],
    },

    // Desktop Chromium — all tests except mobile-specific
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
      testMatch: ['**/tests/**/*.spec.ts'],
      testIgnore: ['**/tests/07-mobile.spec.ts'],
    },

    // Mobile viewport — Pixel 5 (393×851)
    {
      name: 'mobile-chrome',
      use: {
        ...devices['Pixel 5'],
        storageState: 'e2e/.auth/admin.json',
      },
      dependencies: ['setup'],
      testMatch: ['**/tests/07-mobile.spec.ts'],
    },
  ],

  // Starts the Vite dev server if not already running.
  // The dev server proxies /api to localhost:8000 (port-forward the vidya-api service).
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
