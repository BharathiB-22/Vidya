import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, BookOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ProgramStatusBadge } from '@/components/programs/ProgramStatusBadge'
import { CreateProgramDialog } from '@/components/programs/CreateProgramDialog'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { usePrograms } from '@/hooks/programs'
import type { ProgramStatus } from '@/types/program'

const WRITE_ROLES = ['ADMIN', 'DEAN']

const STATUS_OPTIONS: Array<{ value: ProgramStatus | ''; label: string }> = [
  { value: '',                 label: 'All' },
  { value: 'DRAFT',            label: 'Draft' },
  { value: 'AI_GENERATING',    label: 'Generating' },
  { value: 'PENDING_APPROVAL', label: 'Pending Approval' },
  { value: 'APPROVED',         label: 'Approved' },
]

export default function ProgramListPage() {
  const navigate = useNavigate()
  const role = localStorage.getItem('vidya_role') ?? 'FACULTY'
  const canCreate = WRITE_ROLES.includes(role)

  const [statusFilter, setStatusFilter] = useState<ProgramStatus | ''>('')
  const [createOpen, setCreateOpen] = useState(false)

  const { data, isLoading, isError, refetch } = usePrograms(statusFilter ? { status: statusFilter } : undefined)
  const programs = data?.items ?? []

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Programs</h1>
        {canCreate && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1" />
            New Program
          </Button>
        )}
      </div>

      {/* Status filter */}
      <div className="mb-4 flex items-center gap-2 flex-wrap">
        <span className="text-sm text-gray-500">Filter:</span>
        {STATUS_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setStatusFilter(opt.value)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              statusFilter === opt.value
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isLoading && <PageLoading message="Loading programs…" />}

      {isError && (
        <PageError message="Failed to load programs." onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && programs.length === 0 && (
        <PageEmpty
          icon={BookOpen}
          message="No programs found."
          action={canCreate ? (
            <Button variant="outline" size="sm" onClick={() => setCreateOpen(true)}>
              Create your first program
            </Button>
          ) : undefined}
        />
      )}

      {/* Table */}
      {programs.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                {['Title', 'Department', 'Degree', 'Credits', 'Version', 'Status', 'Created'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {programs.map((p) => (
                <tr
                  key={p.id}
                  className="hover:bg-blue-50 cursor-pointer transition-colors"
                  onClick={() => navigate(`/programs/${p.id}`)}
                >
                  <td className="px-4 py-3 text-sm font-medium text-gray-900">{p.title}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{p.department}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{p.degree_type}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">{p.total_credits}</td>
                  <td className="px-4 py-3 text-sm text-gray-500">v{p.version}</td>
                  <td className="px-4 py-3">
                    <ProgramStatusBadge status={p.status} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400">
                    {new Date(p.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div className="px-4 py-2 text-xs text-gray-400 text-right border-t border-gray-100">
            {data?.total ?? 0} program(s)
          </div>
        </div>
      )}

      <CreateProgramDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  )
}
