import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Search, UserCheck, ChevronLeft, ChevronRight,
  CheckSquare, Square, X, UserMinus, Archive, AlertTriangle,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type { FacultyDirectoryItem } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { useAuth } from '@/lib/auth'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'

// ---------------------------------------------------------------------------
// Bulk confirm modal
// ---------------------------------------------------------------------------

function BulkConfirmModal({
  count,
  action,
  onConfirm,
  onCancel,
  isPending,
}: {
  count: number
  action: 'DEACTIVATE' | 'ARCHIVE'
  onConfirm: (reason: string) => void
  onCancel: () => void
  isPending: boolean
}) {
  const [reason, setReason] = useState('')
  const label = action === 'DEACTIVATE' ? 'Deactivate (Set Inactive)' : 'Archive'
  const color = action === 'DEACTIVATE' ? '#fbbf24' : '#f87171'
  const borderColor = action === 'DEACTIVATE' ? 'rgba(251,191,36,0.3)' : 'rgba(239,68,68,0.3)'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="rounded-xl border p-6 max-w-md w-full mx-4 space-y-4"
        style={{ background: '#1a1a2e', borderColor }}>
        <div className="flex items-center gap-3">
          <AlertTriangle size={22} style={{ color }} />
          <h2 className="text-base font-semibold">{label} {count} Faculty Member{count !== 1 ? 's' : ''}?</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          {action === 'DEACTIVATE'
            ? `This will mark ${count} faculty member${count !== 1 ? 's' : ''} as Inactive. They can be reactivated later.`
            : `This will archive ${count} faculty member${count !== 1 ? 's' : ''}. Archived faculty are permanently inactive.`
          }
        </p>
        <input
          type="text"
          placeholder="Reason (optional)"
          value={reason}
          onChange={e => setReason(e.target.value)}
          className="w-full px-3 py-2 text-sm rounded-lg bg-white/5 border border-white/10 text-slate-200 placeholder:text-slate-600"
        />
        <div className="flex gap-3 justify-end pt-1">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={isPending}>Cancel</Button>
          <Button size="sm" onClick={() => onConfirm(reason)} disabled={isPending}
            style={{ background: action === 'DEACTIVATE' ? 'rgba(251,191,36,0.15)' : '#dc2626', color }}>
            {isPending ? 'Applying…' : `Confirm ${label}`}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------------

function InitialsAvatar({ name, color = '#10b981' }: { name: string; color?: string }) {
  const initials = name.split(' ').map(p => p[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-bold"
      style={{ background: `${color}18`, color, border: `1px solid ${color}30` }}>
      {initials}
    </div>
  )
}

function FacultyCard({
  member,
  selectMode,
  selected,
  onToggle,
  onClick,
}: {
  member: FacultyDirectoryItem
  selectMode: boolean
  selected: boolean
  onToggle: () => void
  onClick: () => void
}) {
  return (
    <div
      className="w-full text-left rounded-xl p-4 flex items-start gap-3 transition-all cursor-pointer"
      style={{
        background: selected ? 'rgba(16,185,129,0.08)' : '#ffffff',
        border: selected ? '1px solid rgba(16,185,129,0.35)' : '1px solid #E5E7EB',
      }}
      onClick={selectMode ? onToggle : onClick}
    >
      {selectMode && (
        <div className="flex-shrink-0 mt-0.5">
          {selected
            ? <CheckSquare size={18} style={{ color: '#34d399' }} />
            : <Square size={18} className="text-slate-600" />
          }
        </div>
      )}
      {!selectMode && <InitialsAvatar name={member.full_name} />}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold truncate" style={{ color: '#111827' }}>{member.full_name}</p>
          {member.employee_id && (
            <span className="text-xs px-2 py-0.5 rounded font-mono"
              style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399', border: '1px solid rgba(16,185,129,0.25)' }}>
              {member.employee_id}
            </span>
          )}
          {!member.is_active && (
            <span className="text-xs px-2 py-0.5 rounded"
              style={{ background: 'rgba(239,68,68,0.1)', color: '#f87171' }}>Inactive</span>
          )}
        </div>
        <p className="text-xs mt-0.5 truncate" style={{ color: '#4B5563' }}>{member.email}</p>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
          {member.designation && <span className="text-xs" style={{ color: '#374151' }}>{member.designation}</span>}
          {member.primary_department && <span className="text-xs" style={{ color: '#4B5563' }}>{member.primary_department.name}</span>}
          {member.specialization && <span className="text-xs italic" style={{ color: '#4B5563' }}>{member.specialization}</span>}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function FacultyDirectoryPage() {
  const navigate    = useNavigate()
  const { user }    = useAuth()
  const queryClient = useQueryClient()

  const [search, setSearch]             = useState('')
  const [debouncedSearch, setDebounced] = useState('')
  const [page, setPage]                 = useState(1)
  const [deptId, setDeptId]             = useState<string>('')

  const [selectMode, setSelectMode]     = useState(false)
  const [selected, setSelected]         = useState<Set<string>>(new Set())
  const [bulkAction, setBulkAction]     = useState<'DEACTIVATE' | 'ARCHIVE' | null>(null)

  const PAGE_SIZE = 24
  const canAdmin = user?.role === 'ADMIN'

  function handleSearch(v: string) {
    setSearch(v); setPage(1)
    clearTimeout((handleSearch as any)._t)
    ;(handleSearch as any)._t = setTimeout(() => setDebounced(v), 350)
  }

  const { data, isLoading } = useQuery({
    queryKey: ['sis-faculty-directory', page, PAGE_SIZE, debouncedSearch, deptId],
    queryFn: () => sisApi.listFacultyDirectory({ page, page_size: PAGE_SIZE, search: debouncedSearch || undefined, department_id: deptId || undefined }),
  })

  const { data: departments } = useQuery({
    queryKey: ['acad-departments'],
    queryFn: () => academicsApi.listDepartments(),
  })

  const bulkMut = useMutation({
    mutationFn: ({ action, reason }: { action: 'DEACTIVATE' | 'ARCHIVE'; reason: string }) =>
      sisApi.bulkFacultyAction([...selected], action, reason || undefined),
    onSuccess: (res) => {
      addToast(`${res.succeeded} faculty member${res.succeeded !== 1 ? 's' : ''} ${bulkAction === 'DEACTIVATE' ? 'deactivated' : 'archived'}.${res.failed > 0 ? ` ${res.failed} failed.` : ''}`, res.failed > 0 ? 'error' : 'success')
      setBulkAction(null)
      setSelected(new Set())
      setSelectMode(false)
      queryClient.invalidateQueries({ queryKey: ['sis-faculty-directory'] })
    },
    onError: (e) => { addToast(getErrorMessage(e), 'error'); setBulkAction(null) },
  })

  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1
  const total = data?.total ?? 0

  function toggleSelect(id: string) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selected.size === items.length) setSelected(new Set())
    else setSelected(new Set(items.map(f => f.user_id)))
  }

  function exitSelectMode() { setSelectMode(false); setSelected(new Set()) }

  return (
    <PageShell>
      {bulkAction && (
        <BulkConfirmModal
          count={selected.size}
          action={bulkAction}
          isPending={bulkMut.isPending}
          onCancel={() => setBulkAction(null)}
          onConfirm={(reason) => bulkMut.mutate({ action: bulkAction, reason })}
        />
      )}

      <PageHeader
        icon={UserCheck}
        title="Faculty Directory"
        subtitle={`${total} faculty member${total !== 1 ? 's' : ''} in your institution`}
        action={canAdmin ? (
          !selectMode ? (
            <Button variant="outline" size="sm" onClick={() => setSelectMode(true)} className="gap-1.5">
              <CheckSquare className="h-3.5 w-3.5" /> Select
            </Button>
          ) : undefined
        ) : undefined}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4" style={{ color: '#6B7280' }} />
          <input value={search} onChange={e => handleSearch(e.target.value)}
            placeholder="Search by name, email or employee ID…"
            style={{ color: '#111827' }}
            className="w-full pl-9 pr-4 py-2 rounded-lg text-sm bg-white border border-gray-300 placeholder-gray-400 focus:outline-none focus:border-indigo-500" />
        </div>
        <Select value={deptId || 'ALL'} onValueChange={v => { setDeptId(v === 'ALL' ? '' : v); setPage(1) }}>
          <SelectTrigger className="w-[200px]"><SelectValue placeholder="All departments" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All departments</SelectItem>
            {(departments ?? []).map(d => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Select mode toolbar */}
      {selectMode && (
        <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl"
          style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.18)' }}>
          <button onClick={toggleSelectAll} className="flex items-center gap-1.5 text-xs hover:opacity-80" style={{ color: '#374151' }}>
            {selected.size === items.length && items.length > 0
              ? <CheckSquare size={14} style={{ color: '#10b981' }} />
              : <Square size={14} style={{ color: '#6B7280' }} />
            }
            {selected.size === items.length && items.length > 0 ? 'Deselect all' : 'Select all on page'}
          </button>
          <span className="text-xs" style={{ color: '#4B5563' }}>{selected.size} selected</span>
          <div className="ml-auto flex items-center gap-2">
            {selected.size > 0 && (
              <>
                <Button size="sm" variant="ghost" onClick={() => setBulkAction('DEACTIVATE')}
                  className="gap-1.5 text-xs" style={{ color: '#fbbf24' }}>
                  <UserMinus size={13} /> Deactivate
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setBulkAction('ARCHIVE')}
                  className="gap-1.5 text-xs" style={{ color: '#f87171' }}>
                  <Archive size={13} /> Archive
                </Button>
              </>
            )}
            <button onClick={exitSelectMode} className="p-1 rounded text-slate-500 hover:text-slate-300">
              <X size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Results */}
      {isLoading ? (
        <PageLoading message="Loading faculty directory…" />
      ) : items.length === 0 ? (
        <div className="py-16 text-center">
          <UserCheck className="h-10 w-10 mx-auto mb-3" style={{ color: '#9CA3AF' }} />
          <p className="text-sm" style={{ color: '#4B5563' }}>No faculty members match your filters.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {items.map(f => (
            <FacultyCard
              key={f.user_id}
              member={f}
              selectMode={selectMode}
              selected={selected.has(f.user_id)}
              onToggle={() => toggleSelect(f.user_id)}
              onClick={() => navigate(`/sis/directory/faculty/${f.user_id}`)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 disabled:opacity-30">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-xs" style={{ color: '#4B5563' }}>Page {page} of {totalPages} · {total} total</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 disabled:opacity-30">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </PageShell>
  )
}
