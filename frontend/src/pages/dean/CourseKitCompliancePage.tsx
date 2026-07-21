import { useState } from 'react'
import { ShieldCheck, Package, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { CourseKitStatusBadge } from '@/components/courseKit/CourseKitStatusBadge'
import { useCourseKits, useCourseKitCompliance } from '@/hooks/courseKit'
import type { CourseKitStatus } from '@/types/courseKit'

/**
 * Dean-facing monitoring surface — read-only. Reuses the existing
 * GET /course-kits/{id}/compliance check; does NOT add a new approval gate
 * on the publish workflow (faculty still publish directly, unchanged).
 */

const STATUS_OPTIONS: Array<{ value: CourseKitStatus | ''; label: string }> = [
  { value: '',              label: 'All' },
  { value: 'DRAFT',         label: 'Draft' },
  { value: 'AI_GENERATING', label: 'Generating' },
  { value: 'PUBLISHED',     label: 'Published' },
  { value: 'ARCHIVED',      label: 'Archived' },
]

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="h-4 w-56 rounded bg-gray-200" />
      <div className="mt-1.5 h-3 w-32 rounded bg-gray-100" />
    </div>
  )
}

function ComplianceDialog({ kitId, kitTitle, onClose }: { kitId: string; kitTitle: string; onClose: () => void }) {
  const { data, isLoading, isError } = useCourseKitCompliance(kitId)

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Compliance — {kitTitle}</DialogTitle>
        </DialogHeader>

        {isLoading ? (
          <div className="py-6 space-y-2 animate-pulse">
            <div className="h-4 w-full rounded bg-gray-100" />
            <div className="h-4 w-3/4 rounded bg-gray-100" />
          </div>
        ) : isError ? (
          <p className="text-sm text-red-600 py-4">Failed to load compliance report.</p>
        ) : (
          <div className="py-2 space-y-3">
            <div className={`flex items-center gap-2 text-sm font-semibold ${data?.passed ? 'text-green-700' : 'text-red-700'}`}>
              {data?.passed ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />}
              {data?.passed ? 'Passes compliance checks' : 'Compliance issues found'}
            </div>

            {(data?.violations?.length ?? 0) === 0 ? (
              <p className="text-sm text-gray-500">No violations reported.</p>
            ) : (
              <ul className="space-y-2">
                {data!.violations.map((v, i) => (
                  <li
                    key={i}
                    className={`flex items-start gap-2 rounded-lg px-3 py-2 text-sm ${
                      v.severity === 'ERROR' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'
                    }`}
                  >
                    <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium">{v.code}</p>
                      <p className="text-xs mt-0.5 opacity-90">{v.message}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default function CourseKitCompliancePage() {
  const [statusFilter, setStatusFilter] = useState<CourseKitStatus | ''>('')
  const [selected, setSelected] = useState<{ id: string; title: string } | null>(null)

  const { data, isLoading, isError } = useCourseKits({ status: statusFilter || undefined })
  const kits = data?.items ?? []

  return (
    <PageShell>
      <PageHeader
        icon={ShieldCheck}
        title="Course Kit Compliance"
        subtitle="Monitor course kits across departments — faculty still publish directly; this is a read-only oversight view"
      />

      <div className="flex gap-2 flex-wrap mb-4">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatusFilter(opt.value as CourseKitStatus | '')}
            className={`px-3 py-1 rounded-full text-sm border transition-colors ${
              statusFilter === opt.value
                ? 'bg-gray-900 text-white border-gray-900'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 mb-4">
          Failed to load course kits. Please refresh the page.
        </div>
      )}

      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : kits.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Package className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-600">No course kits found.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {kits.map((kit) => {
            const title = `${kit.course_title ?? 'Untitled Course'} — Unit ${kit.unit_number}`
            return (
              <div key={kit.id} className="flex items-center justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-gray-900 truncate">{title}</h2>
                  <div className="mt-1 flex items-center gap-2 flex-wrap">
                    <CourseKitStatusBadge status={kit.status} />
                    {kit.course_code && (
                      <span className="text-xs text-gray-600">{kit.course_code}</span>
                    )}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setSelected({ id: kit.id, title })}
                  className="shrink-0 text-xs font-semibold px-3 py-1.5 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50"
                >
                  View Compliance
                </button>
              </div>
            )
          })}
        </div>
      )}

      {selected && (
        <ComplianceDialog
          kitId={selected.id}
          kitTitle={selected.title}
          onClose={() => setSelected(null)}
        />
      )}
    </PageShell>
  )
}
