import { ShieldCheck } from 'lucide-react'

// Single source of truth for responsibility-chip colours across the app.
// Previously duplicated in FacultyProfilePage, FacultyDirectoryPage and
// GovernanceDirectoryPage — consolidate here.
export const RESPONSIBILITY_COLORS: Record<string, string> = {
  FACULTY:   '#0ea5e9',
  GUIDE:     '#6366f1',
  EVALUATOR: '#10b981',
  BOARD:     '#f59e0b',
  DEAN:      '#ec4899',
}

export function ResponsibilityChip({ role, withIcon = true }: { role: string; withIcon?: boolean }) {
  const c = RESPONSIBILITY_COLORS[role] ?? '#64748b'
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full"
      style={{ background: `${c}1A`, color: c, border: `1px solid ${c}40` }}
    >
      {withIcon && <ShieldCheck className="h-3 w-3" />}
      {role}
    </span>
  )
}
