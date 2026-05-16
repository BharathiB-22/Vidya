import type { ConfidenceLevel } from '@/types/labs'

const CFG: Record<ConfidenceLevel, { label: string; className: string }> = {
  HIGH:   { label: 'High confidence',   className: 'bg-green-50 text-green-700 border-green-200' },
  MEDIUM: { label: 'Medium confidence', className: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  LOW:    { label: 'Low confidence',    className: 'bg-red-50 text-red-700 border-red-200' },
}

interface Props { level: ConfidenceLevel | null }

export function ConfidenceBadge({ level }: Props) {
  if (!level) return null
  const cfg = CFG[level]
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  )
}
