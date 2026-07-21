import { useNavigate } from 'react-router-dom'
import { GitFork, ExternalLink } from 'lucide-react'
import { useCourseKitVersions } from '@/hooks/courseKit'
import { CourseKitStatusBadge } from './CourseKitStatusBadge'

interface Props {
  kitId:        string
  currentKitId: string
}

export function KitVersionHistory({ kitId, currentKitId }: Props) {
  const navigate = useNavigate()
  const { data: versions, isLoading } = useCourseKitVersions(kitId)

  if (isLoading) {
    return <p className="text-sm text-gray-600 text-center py-6">Loading versions…</p>
  }

  if (!versions || versions.length <= 1) {
    return (
      <p className="text-sm text-gray-600 text-center py-4">
        No other versions — this is the only revision.
      </p>
    )
  }

  const sorted = [...versions].sort((a, b) => b.version - a.version)

  return (
    <div className="rounded-lg border border-gray-200 divide-y divide-gray-100">
      {sorted.map((v) => {
        const isCurrent = v.id === currentKitId
        return (
          <button
            key={v.id}
            type="button"
            disabled={isCurrent}
            onClick={() => navigate(`/course-kits/${v.id}`)}
            className={`w-full text-left flex items-center gap-3 px-4 py-3 transition-colors ${
              isCurrent
                ? 'bg-blue-50 cursor-default'
                : 'hover:bg-gray-50 cursor-pointer group'
            }`}
          >
            <GitFork className="h-4 w-4 text-gray-600 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-gray-700">v{v.version}</span>
                <CourseKitStatusBadge status={v.status} />
                {isCurrent && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">
                    current
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-600 mt-0.5">
                {new Date(v.created_at).toLocaleDateString()}
                {v.published_at && ` · Published ${new Date(v.published_at).toLocaleDateString()}`}
              </p>
            </div>
            {!isCurrent && (
              <ExternalLink className="h-3.5 w-3.5 text-gray-500 group-hover:text-gray-500 shrink-0" />
            )}
          </button>
        )
      })}
    </div>
  )
}
