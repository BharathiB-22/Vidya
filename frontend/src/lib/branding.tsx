import React, { createContext, useContext, useState, useCallback } from 'react'
import api from '@/lib/api'

export interface BrandingState {
  name: string
  logoUrl: string
  primaryColor: string
  accentColor: string
}

const DEFAULTS: BrandingState = {
  name: '',
  logoUrl: '',
  primaryColor: '#2563eb',
  accentColor: '#06b6d4',
}

const LS_NAME   = 'vidya_branding_name'
const LS_LOGO   = 'vidya_institution_logo'
const LS_COLOR  = 'vidya_institution_color'
const LS_COLOR2 = 'vidya_institution_color2'

function readFromStorage(): BrandingState {
  return {
    name:         localStorage.getItem(LS_NAME)   ?? DEFAULTS.name,
    logoUrl:      localStorage.getItem(LS_LOGO)   ?? DEFAULTS.logoUrl,
    primaryColor: localStorage.getItem(LS_COLOR)  ?? DEFAULTS.primaryColor,
    accentColor:  localStorage.getItem(LS_COLOR2) ?? DEFAULTS.accentColor,
  }
}

function writeToStorage(b: BrandingState) {
  localStorage.setItem(LS_NAME,   b.name)
  localStorage.setItem(LS_LOGO,   b.logoUrl)
  localStorage.setItem(LS_COLOR,  b.primaryColor)
  localStorage.setItem(LS_COLOR2, b.accentColor)
}

function clearStorage() {
  localStorage.removeItem(LS_NAME)
  localStorage.removeItem(LS_LOGO)
  localStorage.removeItem(LS_COLOR)
  localStorage.removeItem(LS_COLOR2)
}

interface BrandingContextType {
  branding: BrandingState
  fetchBranding: () => Promise<void>
  clearBranding: () => void
}

const BrandingContext = createContext<BrandingContextType | null>(null)

export function BrandingProvider({ children }: { children: React.ReactNode }) {
  const [branding, setBranding] = useState<BrandingState>(readFromStorage)

  const fetchBranding = useCallback(async () => {
    const slug = localStorage.getItem('vidya_tenant_slug')
    if (!slug) return
    try {
      const { data } = await api.get('/auth/branding')
      const next: BrandingState = {
        name:         data.name          ?? DEFAULTS.name,
        logoUrl:      data.logo_url      ?? DEFAULTS.logoUrl,
        primaryColor: data.primary_color ?? DEFAULTS.primaryColor,
        accentColor:  data.secondary_color ?? DEFAULTS.accentColor,
      }
      setBranding(next)
      writeToStorage(next)
    } catch {
      // Non-fatal: keep localStorage values already in state
    }
  }, [])

  const clearBranding = useCallback(() => {
    setBranding(DEFAULTS)
    clearStorage()
  }, [])

  return (
    <BrandingContext.Provider value={{ branding, fetchBranding, clearBranding }}>
      {children}
    </BrandingContext.Provider>
  )
}

export function useBranding(): BrandingContextType {
  const ctx = useContext(BrandingContext)
  if (!ctx) throw new Error('useBranding must be used inside BrandingProvider')
  return ctx
}
