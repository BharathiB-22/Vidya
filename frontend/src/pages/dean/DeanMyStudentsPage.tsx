import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, GraduationCap, ChevronLeft, ChevronRight, AlertTriangle } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Input } from '@/components/ui/input'
import { sisApi } from '@/lib/api/sis'
import type { StudentDirectoryItem } from '@/lib/api/sis'

function StudentCard({ item, onClick }: { item: StudentDirectoryItem; onClick: () => void }) {
  const initials = item.full_name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <button
      onClick={onClick}
      className="text-left w-full rounded-xl border border-gray-200 bg-white p-4 hover:border-sv-primary/30 hover:shadow-md transition-all duration-150"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-full bg-green-50 border border-green-100 flex items-center justify-center flex-shrink-0">
          <span className="text-sm font-bold text-green-600">{initials}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-semibold text-gray-900 truncate">{item.full_name}</p>
            {!item.is_active && (
              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">Inactive</span>
            )}
          </div>
          {item.usn && (
            <p className="text-xs text-gray-500 font-mono mt-0.5">{item.usn}</p>
          )}
          {item.program && (
            <p className="text-xs text-gray-600 mt-0.5 truncate">{item.program.name}</p>
          )}
          {item.batch && (
            <p className="text-xs text-gray-600 truncate">{item.batch.name}</p>
          )}
        </div>
      </div>
    </button>
  )
}

export default function DeanMyStudentsPage() {
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
    queryKey: ['dean-students', page, search],
    queryFn: () => sisApi.listDeanStudents({
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
        title="My Students"
        subtitle="Students enrolled in programs under your department."
        icon={GraduationCap}
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
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-600" />
            <Input
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="Search by name, email, or USN…"
              className="pl-9"
            />
          </div>
        </div>
      )}

      {(isLoading || profileLoading) && <PageLoading />}

      {error && (
        <div className="text-center py-16 text-red-400 text-sm">
          Failed to load students. Please refresh.
        </div>
      )}

      {!isLoading && !profileLoading && !error && !noDepartment && items.length === 0 && (
        <div className="text-center py-16 text-gray-600 text-sm">
          No students found in your department.
        </div>
      )}

      {!isLoading && !error && items.length > 0 && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(item => (
              <StudentCard
                key={item.user_id}
                item={item}
                onClick={() => navigate(`/sis/directory/students/${item.user_id}`)}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-sm text-gray-500">
                Page {page} of {totalPages} · {data?.total ?? 0} students
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
