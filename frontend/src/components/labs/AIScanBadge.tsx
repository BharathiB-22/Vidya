import type { AIScanStatus } from '@/types/labs'

const CFG: Record<AIScanStatus, { label: string; className: string }> = {
  PENDING: { label: 'Scanning…',  className: 'bg-gray-100 text-gray-500 border-gray-200' },
  CLEAN:   { label: 'AI: Clean',  className: 'bg-green-50 text-green-700 border-green-200' },
  FLAGGED: { label: 'AI: Flagged', className: 'bg-red-50 text-red-700 border-red-200' },
}

interface Props {
  status: AIScanStatus
  probability?: number | null
}

export function AIScanBadge({ status, probability }: Props) {
  const cfg = CFG[status]
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium gap-1 ${cfg.className}`}>
      {cfg.label}
      {probability != null && status === 'FLAGGED' && (
        <span className="opacity-70">({Math.round(probability * 100)}%)</span>
      )}
    </span>
  )
}
