import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, Crown } from 'lucide-react'
import { useWorkspace } from '@/lib/workspace'
import { useGovernance } from '@/lib/governance'
import { useCurrentUser } from '@/hooks/useCurrentUser'

/** Hidden entirely when the user has only one workspace — per spec, nothing
 *  to switch between. */
export function WorkspaceSwitcher() {
  const { activeWorkspace, availableWorkspaces, setActiveWorkspace } = useWorkspace()
  const { bodyLabel } = useGovernance()
  const user = useCurrentUser()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // A Dean who has switched into another workspace (in practice, Faculty) is now
  // scoped EXACTLY like that role server-side — Dean-wide data and Dean actions
  // are gone until they switch back. Surface that so the narrowed view is
  // understood as intentional, and so they know how to regain Dean tools. Only a
  // base DEAN triggers it, so Faculty, Admin and Super Admin never see it.
  const showViewingAsNotice = user?.role === 'DEAN' && activeWorkspace !== 'DEAN'

  // The governance workspace is named by the tenant, not by us: "Board" in one
  // university, "University Members" in another. Every other workspace keeps its
  // static label.
  const labelFor = (key: string, fallback: string) =>
    key === 'BOARD' ? bodyLabel : fallback

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  if (availableWorkspaces.length <= 1) return null

  const current = availableWorkspaces.find((w) => w.key === activeWorkspace) ?? availableWorkspaces[0]

  return (
    <div ref={ref} className="relative px-4 pb-3">
      <p className="text-[9px] font-extrabold text-slate-500 uppercase tracking-[0.16em] mb-1.5">
        Workspace
      </p>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10
                   hover:bg-white/[0.07] transition-colors text-left"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <current.icon className="h-4 w-4 text-sv-accent flex-shrink-0" />
        <span className="flex-1 text-sm font-semibold text-white truncate">
          {labelFor(current.key, current.label)}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {showViewingAsNotice && (
        <div
          className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-amber-400/10 border border-amber-400/20 px-2.5 py-1.5"
          title="You are scoped exactly like a Faculty member here — only your assigned subjects and data, no Dean actions. Switch back to the Dean workspace for department-wide access and Dean tools."
        >
          <Crown className="h-3 w-3 text-amber-300/90 mt-[1px] flex-shrink-0" />
          <span className="text-[10px] font-semibold text-amber-200/90 leading-snug">
            Viewing as {labelFor(current.key, current.label)} · switch to Dean for Dean tools
          </span>
        </div>
      )}

      {open && (
        <div
          role="listbox"
          className="absolute left-4 right-4 mt-1 rounded-xl bg-[#0b1938] border border-white/10 shadow-[0_20px_40px_rgba(0,0,0,0.4)] overflow-hidden z-40"
        >
          {availableWorkspaces.map((w) => {
            const isActive = w.key === activeWorkspace
            return (
              <button
                key={w.key}
                role="option"
                aria-selected={isActive}
                onClick={() => { setActiveWorkspace(w.key); setOpen(false) }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors ${
                  isActive ? 'bg-white/[0.08] text-white font-semibold' : 'text-slate-300 hover:bg-white/[0.06]'
                }`}
              >
                <w.icon className="h-4 w-4 flex-shrink-0" />
                <span className="flex-1 text-left truncate">{labelFor(w.key, w.label)}</span>
                {isActive && <Check className="h-3.5 w-3.5 text-sv-accent flex-shrink-0" />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
