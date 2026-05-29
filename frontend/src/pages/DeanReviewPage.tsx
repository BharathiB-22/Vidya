/**
 * Dean Review Dashboard — overview of all syllabus activity.
 * Shows Department / Program / Course / Faculty / Status / Units / COs / Submitted date.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ClipboardCheck, ChevronRight, Search, RefreshCw } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Input } from '@/components/ui/input'
import api from '@/lib/api'

// ── Types ────────────────────────────────────────────────────────────────────

type SyllabusStatus =
  | 'DRAFT' | 'AI_GENERATING' | 'PENDING_REVIEW'
  | 'DEAN_APPROVED' | 'DEAN_LOCKED'

interface DeanItem {
  id:            string
  status:        SyllabusStatus
  version:       number
  course_id:     string
  course_code:   string
  course_title:  string
  faculty_name:  string | null
  faculty_email: string | null
  unit_count:    number
  co_count:      number
  created_at:    string
  updated_at:    string | null
}

interface DeanOverviewResponse {
  total: number
  items: DeanItem[]
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_LABELS: Record<SyllabusStatus, string> = {
  DRAFT:          'Draft',
  AI_GENERATING:  'Generating',
  PENDING_REVIEW: 'Pending Review',
  DEAN_APPROVED:  'Approved',
  DEAN_LOCKED:    'Locked',
}

const STATUS_CLASSES: Record<SyllabusStatus, string> = {
  DRAFT:          'bg-gray-100 text-gray-600',
  AI_GENERATING:  'bg-yellow-100 text-yellow-700',
  PENDING_REVIEW: 'bg-orange-100 text-orange-700',
  DEAN_APPROVED:  'bg-green-100 text-green-700',
  DEAN_LOCKED:    'bg-blue-100 text-blue-700',
}

const ALL_STATUSES: SyllabusStatus[] = ['PENDING_REVIEW', 'DEAN_APPROVED', 'DEAN_LOCKED', 'DRAFT', 'AI_GENERATING']

function StatusBadge({ status }: { status: SyllabusStatus }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold
                      ${STATUS_CLASSES[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}

function fmt(dt: string | null | undefined) {
  if (!dt) return '—'
  return new Date(dt).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function DeanReviewPage() {
  const navigate = useNavigate()
  const [search,        setSearch]        = useState('')
  const [statusFilter,  setStatusFilter]  = useState<SyllabusStatus[]>(['PENDING_REVIEW'])

  const { data, isLoading, refetch, isFetching } = useQuery<DeanOverviewResponse>({
    queryKey: ['dean-overview', statusFilter],
    queryFn:  () =>
      api
        .get('/syllabi/dean-overview', {
          params: { status: statusFilter, page: 1, page_size: 200 },
          paramsSerializer: (p) =>
            Object.entries(p).flatMap(([k, v]) =>
              Array.isArray(v) ? v.map(val => `${k}=${val}`) : [`${k}=${v}`]
            ).join('&'),
        })
        .then(r => r.data),
  })

  const items = (data?.items ?? []).filter(item => {
    if (!search.trim()) return true
    const q = search.toLowerCase()
    return (
      item.course_code.toLowerCase().includes(q)  ||
      item.course_title.toLowerCase().includes(q) ||
      (item.faculty_name ?? '').toLowerCase().includes(q)
    )
  })

  const pendingCount = (data?.items ?? []).filter(i => i.status === 'PENDING_REVIEW').length

  return (
    <PageShell>
      <PageHeader
        icon={ClipboardCheck}
        title="Dean Review Dashboard"
        subtitle="Overview of all syllabus activity across the institution."
      />

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">

        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-400 pointer-events-none" />
          <Input
            className="pl-8 text-sm"
            placeholder="Search course or faculty…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Status pills */}
        <div className="flex flex-wrap gap-1.5">
          {ALL_STATUSES.map(s => (
            <button
              key={s}
              type="button"
              onClick={() =>
                setStatusFilter(prev =>
                  prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]
                )
              }
              className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                statusFilter.includes(s)
                  ? 'bg-gray-900 text-white border-gray-900'
                  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
              }`}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>

        {/* Refresh */}
        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="p-1.5 rounded-lg border border-gray-200 text-gray-500
                     hover:bg-gray-50 transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Stats bar */}
      {data && (
        <div className="flex gap-6 text-sm">
          <span className="text-gray-500">
            Total: <strong className="text-gray-900">{data.total}</strong>
          </span>
          {pendingCount > 0 && (
            <span className="text-orange-700 font-medium">
              ⚠ {pendingCount} pending review
            </span>
          )}
          {search && (
            <span className="text-gray-500">
              Showing <strong>{items.length}</strong> matching "{search}"
            </span>
          )}
        </div>
      )}

      {/* Table */}
      {isLoading ? (
        <PageLoading />
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-400 rounded-xl border border-dashed border-gray-200">
          {search ? `No syllabuses matching "${search}".` : 'No syllabuses found for the selected filters.'}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 overflow-hidden bg-white">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Course
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Faculty
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Status
                  </th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Units
                  </th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    COs
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Ver.
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Last Updated
                  </th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map((item) => (
                  <tr
                    key={item.id}
                    className="hover:bg-gray-50 cursor-pointer transition-colors group"
                    onClick={() => navigate(`/syllabuses/${item.id}`)}
                  >
                    <td className="px-4 py-3">
                      <p className="font-semibold text-gray-900">{item.course_title}</p>
                      <p className="text-[11px] font-mono text-gray-400 mt-0.5">{item.course_code}</p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-gray-800">{item.faculty_name ?? '—'}</p>
                      {item.faculty_email && (
                        <p className="text-[11px] text-gray-400 mt-0.5">{item.faculty_email}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={item.status} />
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-gray-700">
                      {item.unit_count}
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-gray-700">
                      {item.co_count}
                    </td>
                    <td className="px-4 py-3 text-gray-500 font-mono text-xs">
                      v{item.version}
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs">
                      {fmt(item.updated_at ?? item.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <ChevronRight className="h-4 w-4 text-gray-300 group-hover:text-gray-500" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </PageShell>
  )
}
