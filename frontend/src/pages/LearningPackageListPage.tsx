import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, BookOpen, Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PackageStatusBadge } from '@/components/learningPackage/PackageStatusBadge'
import { useLearningPackages, useTriggerCuration } from '@/hooks/learningPackage'
import type { PackageStatus } from '@/types/learningPackage'

const STATUS_OPTIONS: Array<{ value: PackageStatus | ''; label: string }> = [
  { value: '',          label: 'All'      },
  { value: 'READY',     label: 'Ready'    },
  { value: 'CURATING',  label: 'Curating' },
  { value: 'PENDING',   label: 'Pending'  },
  { value: 'OUTDATED',  label: 'Outdated' },
]

function SkeletonRow() {
  return (
    <div className="px-5 py-4 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-4 w-20 rounded bg-gray-200" />
        <div className="h-5 w-24 rounded-full bg-gray-200" />
      </div>
      <div className="mt-1.5 h-3 w-44 rounded bg-gray-100" />
    </div>
  )
}

export default function LearningPackageListPage() {
  const navigate    = useNavigate()
  const [params]    = useSearchParams()
  const syllabusId  = params.get('syllabus_id') ?? ''
  const unitNumber  = params.get('unit_number') ?? ''

  const role      = localStorage.getItem('vidya_role') ?? ''
  const canCreate = ['ADMIN', 'FACULTY'].includes(role)

  const [statusFilter, setStatusFilter] = useState<PackageStatus | ''>('')
  const triggerCuration = useTriggerCuration()

  function handleGenerate() {
    triggerCuration.mutate(
      { syllabus_id: syllabusId, unit_number: Number(unitNumber) },
      { onSuccess: (data) => navigate(`/learning-packages/${data.package_id}`) },
    )
  }

  const { data, isLoading, isError } = useLearningPackages({
    syllabus_id: syllabusId || undefined,
    status:      statusFilter || undefined,
  })
  const packages = data?.items ?? []

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">

      {/* ── Back ── */}
      {syllabusId && (
        <Button
          variant="ghost"
          size="sm"
          className="-mt-2 -ml-1"
          onClick={() => navigate(-1)}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Back
        </Button>
      )}

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Learning Packages</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {syllabusId
              ? <>Syllabus: <span className="font-mono text-gray-700">{syllabusId}</span></>
              : 'All learning packages in this tenant'}
          </p>
        </div>
      </div>

      {/* ── Status filter pills ── */}
      <div className="flex gap-2 flex-wrap">
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => setStatusFilter(opt.value as PackageStatus | '')}
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

      {/* ── Error ── */}
      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load learning packages. Please refresh the page.
        </div>
      )}

      {/* ── List ── */}
      {isLoading ? (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
          {[1, 2, 3].map((n) => <SkeletonRow key={n} />)}
        </div>
      ) : packages.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">
            {statusFilter
              ? `No packages with status "${statusFilter}".`
              : 'No learning packages yet.'}
          </p>
          {statusFilter ? (
            <button
              type="button"
              onClick={() => setStatusFilter('')}
              className="mt-3 text-xs text-blue-600 underline underline-offset-2"
            >
              Clear filter
            </button>
          ) : unitNumber && canCreate ? (
            <div className="mt-4">
              <p className="text-xs text-gray-400 mb-3">
                Generate an AI-curated package for Unit {unitNumber}.
              </p>
              <Button
                size="sm"
                onClick={handleGenerate}
                disabled={triggerCuration.isPending}
              >
                <Zap className="h-4 w-4 mr-1" />
                {triggerCuration.isPending ? 'Generating…' : `Generate Package for Unit ${unitNumber}`}
              </Button>
              {triggerCuration.isError && (
                <p className="mt-2 text-xs text-red-600">Generation failed — please try again.</p>
              )}
            </div>
          ) : (
            <p className="mt-2 text-xs text-gray-400">
              Open a Course Kit and click "Learning Packages" to create one.
            </p>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {packages.map((pkg) => (
            <button
              key={pkg.id}
              type="button"
              className="w-full text-left px-5 py-4 hover:bg-gray-50 transition-colors group"
              onClick={() => navigate(`/learning-packages/${pkg.id}`)}
            >
              <div className="flex items-center justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                    <span className="text-sm font-semibold text-gray-800">
                      Unit {pkg.unit_number} — v{pkg.version}
                    </span>
                    <PackageStatusBadge status={pkg.status} />
                    <span className="text-xs text-gray-400 tabular-nums">
                      {pkg.item_count} resource{pkg.item_count !== 1 ? 's' : ''}
                    </span>
                  </div>
                  {!syllabusId && (
                    <p className="text-[11px] font-mono text-gray-400 truncate">
                      Syllabus: {pkg.syllabus_id}
                    </p>
                  )}
                  <p className="text-xs text-gray-400">
                    Created {new Date(pkg.created_at).toLocaleDateString()}
                    {pkg.curated_at &&
                      ` · Curated ${new Date(pkg.curated_at).toLocaleDateString()}`}
                  </p>
                </div>
                <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500 shrink-0" />
              </div>
            </button>
          ))}
        </div>
      )}

      {/* ── Pagination hint ── */}
      {data && data.total > packages.length && (
        <p className="text-xs text-gray-400 text-center">
          Showing {packages.length} of {data.total} packages
        </p>
      )}
    </div>
  )
}
