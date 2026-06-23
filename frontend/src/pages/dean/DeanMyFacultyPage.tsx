import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, UserCheck, ChevronLeft, ChevronRight, Building2, AlertTriangle } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Input } from '@/components/ui/input'
import { sisApi } from '@/lib/api/sis'
import type { FacultyDirectoryItem } from '@/lib/api/sis'

const RESP_COLORS: Record<string, string> = {
  GUIDE: '#6366f1', EVALUATOR: '#10b981', BOARD: '#f59e0b', DEAN: '#ec4899',
}

function RespChip({ label }: { label: string }) {
  const bg = RESP_COLORS[label] ?? '#6b7280'
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium"
      style={{ background: `${bg}20`, color: bg, border: `1px solid ${bg}40` }}
    >
      {label}
    </span>
  )
}

function FacultyCard({ item, onClick }: { item: FacultyDirectoryItem; onClick: () => void }) {
  const initials = item.full_name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-xl border border-gray-200 bg-white p-4 hover:border-sv-primary/30 hover:shadow-md transition-all duration-150"
    >
      <div className="flex items-start gap-3">
        {item.photo_url ? (
          <img src={item.photo_url} alt={item.full_name} className="w-10 h-10 rounded-full object-cover flex-shrink-0" />
        ) : (
          <div className="w-10 h-10 rounded-full bg-sv-primary/10 border border-sv-primary/20 flex items-center justify-center flex-shrink-0">
            <span className="text-sm font-bold text-sv-primary">{initials}</span>
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-gray-900 truncate">{item.full_name}</p>
            {!item.is_active && (
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">Inactive</span>
            )}
          </div>
          {item.designation && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{item.designation}</p>
          )}
          {item.primary_department && (
            <div className="flex items-center gap-1 mt-1">
              <Building2 className="h-3 w-3 text-gray-400" />
              <span className="text-xs text-gray-400 truncate">{item.primary_department.name}</span>
            </div>
          )}
          {item.responsibilities.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1.5">
              {item.responsibilities.map(r => <RespChip key={r} label={r} />)}
            </div>
          )}
        </div>
      </div>
    </button>
  )
}

export default function DeanMyFacultyPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ['dean-my-profile'],
    queryFn: () => sisApi.getMyFacultyProfile(),
    staleTime: 5 * 60 * 1000,
  })

  const noDepartment = !profileLoading && !profile?.primary_department

  const { data, isLoading, error } = useQuery({
    queryKey: ['dean-faculty', page, search],
    queryFn: () => sisApi.listDeanFaculty({
      page,
      page_size: pageSize,
      search: search || undefined,
    }),
    enabled: !noDepartment,
    placeholderData: prev => prev,
  })

  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1

  return (
    <PageShell>
      <PageHeader
        title="My Faculty"
        subtitle="Faculty in your department — by primary assignment or active teaching."
        icon={UserCheck}
      />

      {noDepartment && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-800">Department not assigned</p>
            <p className="text-sm text-amber-700 mt-0.5">
              Your account has no department set. Ask an administrator to assign your department
              via <strong>Settings → Users</strong>, then edit your account.
            </p>
          </div>
        </div>
      )}

      {!noDepartment && (
        <div className="flex gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Search by name or email…"
              className="pl-9"
            />
          </div>
        </div>
      )}

      {(isLoading || profileLoading) && <PageLoading />}

      {error && (
        <div className="text-center py-16 text-red-400 text-sm">
          Failed to load faculty. Please refresh.
        </div>
      )}

      {!isLoading && !profileLoading && !error && !noDepartment && items.length === 0 && (
        <div className="text-center py-16 text-gray-400 text-sm">
          No faculty found in your department.
        </div>
      )}

      {!isLoading && !error && items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(item => (
              <FacultyCard
                key={item.user_id}
                item={item}
                onClick={() => navigate(`/sis/directory/faculty/${item.user_id}`)}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-sm text-gray-500">
                Page {page} of {totalPages} · {data?.total ?? 0} faculty
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-1.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <button
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="p-1.5 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </PageShell>
  )
}
