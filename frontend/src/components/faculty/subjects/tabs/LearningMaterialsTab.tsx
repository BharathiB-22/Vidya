import { useNavigate } from 'react-router-dom'
import { Library, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PackageStatusBadge } from '@/components/learningPackage/PackageStatusBadge'
import { useLearningPackages } from '@/hooks/learningPackage'
import type { FacultySubjectTabProps } from './types'

export function LearningMaterialsTab({ ctx }: FacultySubjectTabProps) {
  const navigate = useNavigate()
  const { syllabusId } = ctx

  const { data, isLoading, isError } = useLearningPackages({ syllabus_id: syllabusId ?? undefined })
  const items = data?.items ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">
          {data ? `${data.total} package${data.total !== 1 ? 's' : ''}` : 'Learning Materials'}
        </p>
        <Button
          size="sm"
          onClick={() => navigate(`/learning-packages${syllabusId ? `?syllabus_id=${syllabusId}` : ''}`)}
        >
          <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
          Open Learning Materials
        </Button>
      </div>

      {isLoading ? (
        <div className="text-sm text-gray-600 py-8 text-center">Loading learning materials…</div>
      ) : isError ? (
        <div className="text-sm text-gray-600 py-8 text-center">Failed to load learning materials.</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 rounded-xl border border-dashed border-gray-200">
          <Library className="h-8 w-8 mx-auto mb-2 text-gray-200" />
          <p className="text-sm text-gray-600">No learning packages curated yet for this subject.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => navigate(`/learning-packages/${p.id}`)}
              className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">Unit {p.unit_number}</p>
                <p className="text-xs text-gray-600">{p.item_count} item{p.item_count !== 1 ? 's' : ''} · v{p.version}</p>
              </div>
              <PackageStatusBadge status={p.status} />
            </button>
          ))}
        </div>
      )}

      <p className="text-xs text-gray-600">
        Faculty notes, slides, videos, and PDFs are curated inside the existing Learning Materials editor.
      </p>
    </div>
  )
}
