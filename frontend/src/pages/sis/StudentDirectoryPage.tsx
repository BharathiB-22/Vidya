import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, Users, GraduationCap, ChevronLeft, ChevronRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi } from '@/lib/api/sis'
import type { StudentDirectoryItem } from '@/lib/api/sis'
import { useQuery as useAcadQuery } from '@tanstack/react-query'
import { academicsApi } from '@/lib/api/academics'

function InitialsAvatar({ name }: { name: string }) {
  const initials = name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div
      className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold"
      style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.3)' }}
    >
      {initials}
    </div>
  )
}

function StudentCard({ student, onClick }: { student: StudentDirectoryItem; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl p-4 flex items-start gap-3 transition-all hover:scale-[1.01] cursor-pointer"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <InitialsAvatar name={student.full_name} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-slate-200 truncate">{student.full_name}</p>
          {student.usn && (
            <span
              className="text-xs px-2 py-0.5 rounded font-mono"
              style={{ background: 'rgba(99,102,241,0.15)', color: '#a5b4fc', border: '1px solid rgba(99,102,241,0.25)' }}
            >
              {student.usn}
            </span>
          )}
          {!student.is_active && (
            <span className="text-xs px-2 py-0.5 rounded" style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>
              Inactive
            </span>
          )}
        </div>
        <p className="text-xs text-slate-500 mt-0.5 truncate">{student.email}</p>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {student.program && (
            <span className="text-xs text-slate-400">
              {student.program.name} · {student.program.degree_type}
            </span>
          )}
          {student.batch && (
            <span className="text-xs text-slate-500">
              Batch {student.batch.start_year}–{student.batch.end_year}
            </span>
          )}
          {student.current_section && (
            <span className="text-xs text-slate-500">
              Sec {student.current_section.name}
            </span>
          )}
          {student.admission_year && (
            <span className="text-xs text-slate-500">
              Admitted {student.admission_year}
            </span>
          )}
        </div>
      </div>
    </button>
  )
}

export default function StudentDirectoryPage() {
  const navigate = useNavigate()
  const [search, setSearch]           = useState('')
  const [debouncedSearch, setDebounced] = useState('')
  const [page, setPage]               = useState(1)
  const [programId, setProgramId]     = useState<string>('')
  const [batchId, setBatchId]         = useState<string>('')
  const PAGE_SIZE = 24

  // Debounce search input
  function handleSearch(v: string) {
    setSearch(v)
    setPage(1)
    clearTimeout((handleSearch as any)._t)
    ;(handleSearch as any)._t = setTimeout(() => setDebounced(v), 350)
  }

  const { data, isLoading } = useQuery({
    queryKey: ['sis-student-directory', page, PAGE_SIZE, debouncedSearch, programId, batchId],
    queryFn: () => sisApi.listStudentDirectory({
      page,
      page_size: PAGE_SIZE,
      search: debouncedSearch || undefined,
      program_id: programId || undefined,
      batch_id: batchId || undefined,
    }),
  })

  const { data: programs } = useAcadQuery({
    queryKey: ['acad-programs'],
    queryFn: () => academicsApi.listPrograms(),
  })

  const { data: batches } = useAcadQuery({
    queryKey: ['acad-batches', programId],
    queryFn: () => academicsApi.listBatches(programId || undefined),
    enabled: true,
  })

  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1
  const total = data?.total ?? 0

  return (
    <PageShell>
      <PageHeader
        icon={Users}
        title="Student Directory"
        subtitle={`${total} student${total !== 1 ? 's' : ''} in your institution`}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500" />
          <input
            value={search}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search by name, email or USN…"
            className="w-full pl-9 pr-4 py-2 rounded-lg text-sm bg-white/5 border border-white/10 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <select
          value={programId}
          onChange={e => { setProgramId(e.target.value); setBatchId(''); setPage(1) }}
          className="px-3 py-2 rounded-lg text-sm bg-white/5 border border-white/10 text-slate-300"
        >
          <option value="">All programs</option>
          {(programs ?? []).map(p => (
            <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
          ))}
        </select>

        <select
          value={batchId}
          onChange={e => { setBatchId(e.target.value); setPage(1) }}
          className="px-3 py-2 rounded-lg text-sm bg-white/5 border border-white/10 text-slate-300"
        >
          <option value="">All batches</option>
          {(batches ?? []).filter(b => !programId || b.program_id === programId).map(b => (
            <option key={b.id} value={b.id}>{b.name} ({b.start_year}–{b.end_year})</option>
          ))}
        </select>
      </div>

      {/* Results */}
      {isLoading ? (
        <PageLoading message="Loading student directory…" />
      ) : items.length === 0 ? (
        <div className="py-16 text-center">
          <GraduationCap className="h-10 w-10 text-slate-700 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No students match your filters.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map(s => (
            <StudentCard
              key={s.user_id}
              student={s}
              onClick={() => navigate(`/sis/directory/students/${s.user_id}`, { state: { from: 'directory' } })}
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
