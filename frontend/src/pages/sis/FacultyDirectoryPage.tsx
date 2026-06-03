import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, UserCheck, ChevronLeft, ChevronRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi } from '@/lib/api/sis'
import type { FacultyDirectoryItem } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'

function InitialsAvatar({ name, color = '#10b981' }: { name: string; color?: string }) {
  const initials = name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div
      className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold"
      style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}
    >
      {initials}
    </div>
  )
}

function FacultyCard({ member, onClick }: { member: FacultyDirectoryItem; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl p-4 flex items-start gap-3 transition-all hover:scale-[1.01] cursor-pointer"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <InitialsAvatar name={member.full_name} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-slate-200 truncate">{member.full_name}</p>
          {member.employee_id && (
            <span
              className="text-xs px-2 py-0.5 rounded font-mono"
              style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399', border: '1px solid rgba(16,185,129,0.25)' }}
            >
              {member.employee_id}
            </span>
          )}
          {!member.is_active && (
            <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>
              Inactive
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-0.5 truncate">{member.email}</p>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
          {member.designation && (
            <span className="text-xs text-slate-400">{member.designation}</span>
          )}
          {member.primary_department && (
            <span className="text-xs text-slate-500">{member.primary_department.name}</span>
          )}
          {member.specialization && (
            <span className="text-xs text-slate-500 italic">{member.specialization}</span>
          )}
        </div>
      </div>
    </button>
  )
}

export default function FacultyDirectoryPage() {
  const navigate = useNavigate()
  const [search, setSearch]             = useState('')
  const [debouncedSearch, setDebounced] = useState('')
  const [page, setPage]                 = useState(1)
  const [deptId, setDeptId]             = useState<string>('')
  const PAGE_SIZE = 24

  function handleSearch(v: string) {
    setSearch(v)
    setPage(1)
    clearTimeout((handleSearch as any)._t)
    ;(handleSearch as any)._t = setTimeout(() => setDebounced(v), 350)
  }

  const { data, isLoading } = useQuery({
    queryKey: ['sis-faculty-directory', page, PAGE_SIZE, debouncedSearch, deptId],
    queryFn: () => sisApi.listFacultyDirectory({
      page,
      page_size: PAGE_SIZE,
      search: debouncedSearch || undefined,
      department_id: deptId || undefined,
    }),
  })

  const { data: departments } = useQuery({
    queryKey: ['acad-departments'],
    queryFn: () => academicsApi.listDepartments(),
  })

  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1
  const total = data?.total ?? 0

  return (
    <PageShell>
      <PageHeader
        icon={UserCheck}
        title="Faculty Directory"
        subtitle={`${total} faculty member${total !== 1 ? 's' : ''} in your institution`}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            value={search}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search by name, email or employee ID…"
            className="w-full pl-9 pr-4 py-2 rounded-lg text-sm bg-white/5 border border-white/10 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <select
          value={deptId}
          onChange={e => { setDeptId(e.target.value); setPage(1) }}
          className="px-3 py-2 rounded-lg text-sm bg-white/5 border border-white/10 text-slate-300"
        >
          <option value="">All departments</option>
          {(departments ?? []).map(d => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>
      </div>

      {/* Results */}
      {isLoading ? (
        <PageLoading message="Loading faculty directory…" />
      ) : items.length === 0 ? (
        <div className="py-16 text-center">
          <UserCheck className="h-10 w-10 text-slate-700 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No faculty members match your filters.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map(f => (
            <FacultyCard
              key={f.user_id}
              member={f}
              onClick={() => navigate(`/sis/directory/faculty/${f.user_id}`)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 disabled:opacity-30"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-xs text-slate-500">
            Page {page} of {totalPages} · {total} total
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </PageShell>
  )
}
