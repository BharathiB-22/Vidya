import { Eye } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { AIScanBadge } from '@/components/labs/AIScanBadge'
import type { LabSubmission, SubmissionStatus } from '@/types/labs'

const SUB_STATUS_CFG: Record<SubmissionStatus, { label: string; cls: string }> = {
  SUBMITTED:  { label: 'Submitted',  cls: 'text-blue-700 bg-blue-50' },
  EVALUATING: { label: 'Evaluating', cls: 'text-yellow-700 bg-yellow-50' },
  EVALUATED:  { label: 'Evaluated',  cls: 'text-purple-700 bg-purple-50' },
  REVIEWED:   { label: 'Reviewed',   cls: 'text-indigo-700 bg-indigo-50' },
  RATIFIED:   { label: 'Ratified',   cls: 'text-green-700 bg-green-50' },
}

export function SubmissionRow({ sub, onReview }: { sub: LabSubmission; onReview: () => void }) {
  const cfg = SUB_STATUS_CFG[sub.status] ?? { label: sub.status, cls: 'text-gray-500 bg-gray-50' }
  const canReview = sub.status === 'EVALUATED' || sub.status === 'REVIEWED' || sub.status === 'RATIFIED'
  return (
    <div className="px-5 py-3 flex items-center justify-between gap-4 hover:bg-gray-50 transition-colors">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-mono text-gray-700 truncate">{sub.student_user_id}</p>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.cls}`}>{cfg.label}</span>
          <AIScanBadge status={sub.ai_scan_status} />
          {sub.is_late && (
            <span className="text-xs text-orange-600 bg-orange-50 px-1.5 py-0.5 rounded">Late</span>
          )}
          <span className="text-xs text-gray-400">{new Date(sub.submitted_at).toLocaleDateString()}</span>
        </div>
      </div>
      {canReview && (
        <Button size="sm" variant="ghost" onClick={onReview} className="shrink-0 text-gray-600">
          <Eye className="h-3.5 w-3.5 mr-1" />
          Review
        </Button>
      )}
    </div>
  )
}
