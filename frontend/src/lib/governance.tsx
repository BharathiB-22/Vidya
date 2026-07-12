import { createContext, useContext, useMemo } from 'react'
import type { ReactNode } from 'react'
import { useGovernanceInfo } from '@/hooks/governance'
import { useAuth } from '@/lib/auth'
import type { GovernanceInfo } from '@/types/governance'

/**
 * Governance vocabulary, tenant-wide.
 *
 * University A calls its curriculum authority a "Board". University B calls it
 * "University Members". They behave identically — only the words differ. Every
 * governance surface reads its label from here instead of hardcoding "Board",
 * so one tenant's UI never shows another tenant's vocabulary.
 *
 * Falls back to Board while loading or if the request fails, which is what the
 * platform said before this concept existed.
 */
const FALLBACK: GovernanceInfo = {
  governance_type: 'BOARD',
  body_label: 'Board',
  member_label: 'Board Member',
}

const GovernanceContext = createContext<GovernanceInfo>(FALLBACK)

export function GovernanceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()
  const { data } = useGovernanceInfo(isAuthenticated)
  const value = useMemo(() => data ?? FALLBACK, [data])
  return <GovernanceContext.Provider value={value}>{children}</GovernanceContext.Provider>
}

/** `const { bodyLabel } = useGovernance()` → "Board" or "University Members". */
export function useGovernance(): {
  governanceType: GovernanceInfo['governance_type']
  bodyLabel: string
  memberLabel: string
} {
  const info = useContext(GovernanceContext)
  return {
    governanceType: info.governance_type,
    bodyLabel: info.body_label,
    memberLabel: info.member_label,
  }
}
