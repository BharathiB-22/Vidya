import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Crown, BookOpen, GraduationCap, ShieldCheck, Landmark } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useAuth, effectiveRoles } from '@/lib/auth'

// Flat key read by the axios interceptor (outside React) to stamp every request
// with X-Active-Workspace. Kept in sync with the active workspace below.
const ACTIVE_WORKSPACE_KEY = 'vidya_active_workspace'

export interface WorkspaceDef {
  /** The TenantRole value that defines this workspace (base role or grant). */
  key: string
  label: string
  icon: LucideIcon
  homeRoute: string
}

// Workspaces that already have a full, standalone sidebar + dashboard today —
// these are the only complete application workspaces. GUIDE and EVALUATOR are
// FACULTY responsibilities, not workspaces: they never appear here, and stay
// exactly as they are today — grant-overlay items nested inside whichever of
// these workspaces is active (see Sidebar.tsx's `grantOverlay` items, e.g.
// "My Responsibilities" under Dean, "Evaluate"/"Research" under Faculty).
// Add a new workspace here (and it needs nothing else) once its own
// dedicated navigation exists (e.g. Board).
// BOARD is a full workspace as of Phase A: the governance authority now owns the
// curriculum and has its own navigation (Curriculum Review, Approved Curricula).
// Its label is intentionally NOT hardcoded here — a tenant may call it "Board" or
// "University Members" — so the switcher overrides `label` at render time from
// `useGovernance()`. See WorkspaceSwitcher and Sidebar.
export const WORKSPACES: WorkspaceDef[] = [
  { key: 'ADMIN',   label: 'Admin',   icon: ShieldCheck,   homeRoute: '/dashboard' },
  { key: 'DEAN',    label: 'Dean',    icon: Crown,          homeRoute: '/dashboard' },
  { key: 'BOARD',   label: 'Board',   icon: Landmark,       homeRoute: '/governance/curriculum' },
  { key: 'FACULTY', label: 'Faculty', icon: BookOpen,       homeRoute: '/dashboard' },
  { key: 'STUDENT', label: 'Student', icon: GraduationCap,  homeRoute: '/dashboard' },
]

const STORAGE_PREFIX = 'vidya:workspace:'

interface WorkspaceContextType {
  /** The single active workspace driving nav/dashboard visibility right now. */
  activeWorkspace: string
  /** Workspaces this user may switch into, in WORKSPACES display order. */
  availableWorkspaces: WorkspaceDef[]
  setActiveWorkspace: (key: string) => void
}

const WorkspaceContext = createContext<WorkspaceContextType | null>(null)

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const roleSet = useMemo(() => effectiveRoles(user), [user])
  const availableWorkspaces = useMemo(
    () => WORKSPACES.filter((w) => roleSet.has(w.key)),
    [roleSet],
  )

  const [activeWorkspace, setActiveWorkspaceState] = useState<string>(user?.role ?? '')

  // Mirror the active workspace into the flat key the request interceptor reads,
  // so every outgoing request carries the matching X-Active-Workspace. Cleared
  // when there is no user (logout) so a stale workspace never leaks into the
  // next session's requests.
  useEffect(() => {
    if (user && activeWorkspace) localStorage.setItem(ACTIVE_WORKSPACE_KEY, activeWorkspace)
    else localStorage.removeItem(ACTIVE_WORKSPACE_KEY)
  }, [user, activeWorkspace])

  // Resolve the active workspace whenever the logged-in user changes: the
  // last workspace persisted for THIS user if it's still valid for them,
  // otherwise their primary (base login) role. Scoped per user.id so a
  // shared browser / different login never inherits another account's choice.
  useEffect(() => {
    if (!user) return
    const stored = localStorage.getItem(`${STORAGE_PREFIX}${user.id}`)
    const valid = stored && availableWorkspaces.some((w) => w.key === stored)
    setActiveWorkspaceState(valid ? stored! : user.role)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id])

  function setActiveWorkspace(key: string) {
    if (!availableWorkspaces.some((w) => w.key === key)) return
    if (key === activeWorkspace) return
    setActiveWorkspaceState(key)
    if (user) localStorage.setItem(`${STORAGE_PREFIX}${user.id}`, key)
    localStorage.setItem(ACTIVE_WORKSPACE_KEY, key)
    // The workspace IS the server-side data scope now: every cached query was
    // fetched under the old viewing role. Drop the cache so everything refetches
    // under the new X-Active-Workspace — otherwise Dean-scoped data would linger
    // after switching to Faculty (and vice-versa).
    queryClient.clear()
    const def = WORKSPACES.find((w) => w.key === key)
    navigate(def?.homeRoute ?? '/dashboard')
  }

  return (
    <WorkspaceContext.Provider value={{ activeWorkspace, availableWorkspaces, setActiveWorkspace }}>
      {children}
    </WorkspaceContext.Provider>
  )
}

export function useWorkspace(): WorkspaceContextType {
  const ctx = useContext(WorkspaceContext)
  if (!ctx) throw new Error('useWorkspace must be used within a WorkspaceProvider')
  return ctx
}
