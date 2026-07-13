import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

/* ---------------------------------------------------------------------------
 * Theme state for the Platform Console (Super Admin) — and nothing else.
 *
 * The chosen theme is published as a `data-pc-theme` attribute on the shell's
 * root element, which is the only thing src/styles/platform-theme.css keys off.
 * Tenant portals render outside that subtree, so they cannot inherit a theme
 * even by accident.
 * ------------------------------------------------------------------------- */

export const PLATFORM_THEMES = ['blue', 'white', 'black'] as const

export type PlatformTheme = (typeof PLATFORM_THEMES)[number]

export const DEFAULT_PLATFORM_THEME: PlatformTheme = 'blue'

/* Deliberately not the auth token's key prefix: logout clears the token, and
   the theme is expected to outlive the session and be restored at next login. */
const STORAGE_KEY = 'vidya_platform_theme'

export const PLATFORM_THEME_LABELS: Record<PlatformTheme, { name: string; swatch: string }> = {
  blue:  { name: 'Blue',  swatch: '🔵' },
  white: { name: 'White', swatch: '⚪' },
  black: { name: 'Black', swatch: '⚫' },
}

function isPlatformTheme(value: unknown): value is PlatformTheme {
  return typeof value === 'string' && (PLATFORM_THEMES as readonly string[]).includes(value)
}

function readStoredTheme(): PlatformTheme {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return isPlatformTheme(stored) ? stored : DEFAULT_PLATFORM_THEME
  } catch {
    // Private browsing / storage disabled — the console still works, it just
    // opens on the default every time.
    return DEFAULT_PLATFORM_THEME
  }
}

interface PlatformThemeContextValue {
  theme: PlatformTheme
  setTheme: (theme: PlatformTheme) => void
}

const PlatformThemeContext = createContext<PlatformThemeContextValue | null>(null)

export function PlatformThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<PlatformTheme>(readStoredTheme)

  const setTheme = useCallback((next: PlatformTheme) => {
    setThemeState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Non-fatal: the switch still applies for this session.
    }
  }, [])

  /* Keep multiple open console tabs in agreement. */
  useEffect(() => {
    function onStorage(event: StorageEvent) {
      if (event.key === STORAGE_KEY && isPlatformTheme(event.newValue)) {
        setThemeState(event.newValue)
      }
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const value = useMemo(() => ({ theme, setTheme }), [theme, setTheme])

  return <PlatformThemeContext.Provider value={value}>{children}</PlatformThemeContext.Provider>
}

export function usePlatformTheme(): PlatformThemeContextValue {
  const ctx = useContext(PlatformThemeContext)
  if (!ctx) throw new Error('usePlatformTheme must be used inside PlatformThemeProvider')
  return ctx
}
