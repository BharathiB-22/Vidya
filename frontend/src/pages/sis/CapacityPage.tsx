import { useMemo, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Gauge, AlertTriangle, CheckCircle, XCircle, AlertOctagon,
  Edit2, X, Check, ArrowUpDown,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type { SectionCapacityOut, CapacityStatus } from '@/lib/api/sis'
import { useAuth } from '@/lib/auth'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'

// ---------------------------------------------------------------------------
// Status colour system
//   Green     = Healthy
//   Amber     = Near Full (>80%)
//   Red       = Full (100%)
//   Dark red  = Over Capacity
// ---------------------------------------------------------------------------

const STATUS_META: Record<CapacityStatus, { color: string; label: string; Icon: typeof CheckCircle }> = {
  HEALTHY:   { color: '#16A34A', label: 'Healthy',        Icon: CheckCircle },
  NEAR_FULL: { color: '#D97706', label: 'Near full',      Icon: AlertTriangle },
  FULL:      { color: '#DC2626', label: 'Full',           Icon: XCircle },
  OVER:      { color: '#991B1B', label: 'Over capacity',  Icon: AlertOctagon },
  NO_CAP:    { color: '#6B7280', label: 'No cap set',     Icon: Gauge },
}

function StatusIcon({ status }: { status: CapacityStatus }) {
  const { color, Icon, label } = STATUS_META[status]
  return <Icon size={16} style={{ color }} aria-label={label} />
}

function FillBar({ pct, status }: { pct: number | null; status: CapacityStatus }) {
  if (pct === null) {
    return <span className="text-xs italic" style={{ color: '#6B7280' }}>No cap set</span>
  }
  const { color } = STATUS_META[status]
  const clamped = Math.min(pct, 100)
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: '#E5E7EB' }}>
        <div className="h-full rounded-full transition-all" style={{ width: `${clamped}%`, background: color }} />
      </div>
      <span className="text-xs font-semibold tabular-nums w-12 text-right" style={{ color }}>{pct}%</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Inline capacity editor cell
// ---------------------------------------------------------------------------

function CapacityCell({
  row, canEdit, onSave, isSaving,
}: {
  row: SectionCapacityOut
  canEdit: boolean
  onSave: (sectionId: string, val: number | null) => void
  isSaving: boolean
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft]     = useState('')

  function startEdit() {
    setDraft(row.max_strength != null ? String(row.max_strength) : '')
    setEditing(true)
  }

  function commit() {
    const parsed = draft.trim() === '' ? null : parseInt(draft, 10)
    if (draft.trim() !== '' && (isNaN(parsed!) || parsed! < 1)) {
      addToast('Capacity must be a positive integer or blank to remove.', 'error')
      return
    }
    onSave(row.section_id, parsed)
    setEditing(false)
  }

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input
          type="number" min={1} value={draft} autoFocus
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
          className="w-20 px-2 py-1 text-sm rounded bg-white border border-indigo-500 text-gray-900"
          placeholder="e.g. 60"
        />
        <button onClick={commit} disabled={isSaving} className="text-emerald-600 hover:text-emerald-700">
          <Check size={15} />
        </button>
        <button onClick={() => setEditing(false)} className="text-gray-600 hover:text-gray-600">
          <X size={15} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 group/cap">
      <span className="text-sm font-semibold tabular-nums" style={{ color: row.max_strength != null ? '#111827' : '#9CA3AF' }}>
        {row.max_strength != null ? row.max_strength : '—'}
      </span>
      {canEdit && (
        <button
          onClick={startEdit}
          className="opacity-0 group-hover/cap:opacity-100 transition-opacity text-gray-600 hover:text-indigo-600"
          aria-label="Edit capacity"
        >
          <Edit2 size={13} />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Summary card
// ---------------------------------------------------------------------------

function SummaryCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl bg-white border border-gray-200 px-4 py-3 min-w-[140px] flex-1">
      <p className="text-2xl font-bold tabular-nums" style={{ color }}>{value.toLocaleString()}</p>
      <p className="text-xs mt-0.5" style={{ color: '#4B5563' }}>{label}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Filter dropdown helper
// ---------------------------------------------------------------------------

interface Opt { value: string; label: string }

function FilterSelect({
  value, onChange, options, allLabel, width = 'w-[170px]',
}: {
  value: string
  onChange: (v: string) => void
  options: Opt[]
  allLabel: string
  width?: string
}) {
  return (
    <Select value={value || 'ALL'} onValueChange={v => onChange(v === 'ALL' ? '' : v)}>
      <SelectTrigger className={width}><SelectValue placeholder={allLabel} /></SelectTrigger>
      <SelectContent>
        <SelectItem value="ALL">{allLabel}</SelectItem>
        {options.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
      </SelectContent>
    </Select>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type SortKey = 'fill' | 'capacity' | 'enrollment'

export default function CapacityPage() {
  const { user }    = useAuth()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState<string | null>(null)

  const [school, setSchool]         = useState('')
  const [department, setDepartment] = useState('')
  const [program, setProgram]       = useState('')
  const [batch, setBatch]           = useState('')
  const [semester, setSemester]     = useState('')
  const [sortKey, setSortKey]       = useState<SortKey>('fill')
  const [sortDir, setSortDir]       = useState<'asc' | 'desc'>('desc')

  const canEdit = user?.role === 'ADMIN'

  const { data, isLoading } = useQuery({
    queryKey: ['sis-capacity'],
    queryFn: () => sisApi.listSectionsCapacity(),
  })

  const setMut = useMutation({
    mutationFn: ({ sectionId, val }: { sectionId: string; val: number | null }) =>
      sisApi.setSectionCapacity(sectionId, val),
    onMutate: ({ sectionId }) => setSaving(sectionId),
    onSuccess: () => {
      addToast('Capacity updated.', 'success')
      queryClient.invalidateQueries({ queryKey: ['sis-capacity'] })
    },
    onError: (e) => addToast(getErrorMessage(e), 'error'),
    onSettled: () => setSaving(null),
  })

  const allRows = data ?? []

  // Distinct filter options derived from the full dataset
  const opts = useMemo(() => {
    const uniq = (pairs: [string | null, string | null][]) => {
      const m = new Map<string, string>()
      for (const [v, l] of pairs) if (v && l) m.set(v, l)
      return [...m.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label))
    }
    const sems = new Map<string, string>()
    for (const r of allRows) {
      if (r.semester_number != null) {
        sems.set(String(r.semester_number), r.semester_label || `Semester ${r.semester_number}`)
      }
    }
    return {
      school:     uniq(allRows.map(r => [r.school_id, r.school_name])),
      department: uniq(allRows.map(r => [r.department_id, r.department_name])),
      program:    uniq(allRows.map(r => [r.program_id, r.program_code ? `${r.program_name} (${r.program_code})` : r.program_name])),
      batch:      uniq(allRows.map(r => [r.batch_id, r.batch_name])),
      semester:   [...sems.entries()].map(([value, label]) => ({ value, label }))
                    .sort((a, b) => Number(a.value) - Number(b.value)),
    }
  }, [allRows])

  // Apply filters
  const filtered = useMemo(() => allRows.filter(r =>
    (!school     || r.school_id === school) &&
    (!department || r.department_id === department) &&
    (!program    || r.program_id === program) &&
    (!batch      || r.batch_id === batch) &&
    (!semester   || String(r.semester_number) === semester)
  ), [allRows, school, department, program, batch, semester])

  // Sort
  const rows = useMemo(() => {
    const val = (r: SectionCapacityOut) =>
      sortKey === 'capacity' ? (r.max_strength ?? -1)
      : sortKey === 'enrollment' ? r.enrolled
      : (r.fill_pct ?? -1)
    const sorted = [...filtered].sort((a, b) => val(a) - val(b))
    return sortDir === 'desc' ? sorted.reverse() : sorted
  }, [filtered, sortKey, sortDir])

  // Summary stats (computed over the filtered view)
  const stats = useMemo(() => {
    const totalSeats = filtered.reduce((s, r) => s + (r.max_strength ?? 0), 0)
    const totalStudents = filtered.reduce((s, r) => s + r.enrolled, 0)
    return {
      sections: filtered.length,
      seats: totalSeats,
      students: totalStudents,
      nearFull: filtered.filter(r => r.status === 'NEAR_FULL').length,
      full: filtered.filter(r => r.status === 'FULL').length,
      over: filtered.filter(r => r.status === 'OVER').length,
    }
  }, [filtered])

  const anyFilter = school || department || program || batch || semester
  function clearFilters() { setSchool(''); setDepartment(''); setProgram(''); setBatch(''); setSemester('') }

  const HEAD: { key: string; label: string; align?: string }[] = [
    { key: 'status', label: '' },
    { key: 'school', label: 'School' },
    { key: 'department', label: 'Department' },
    { key: 'program', label: 'Program' },
    { key: 'batch', label: 'Batch' },
    { key: 'semester', label: 'Sem' },
    { key: 'section', label: 'Section' },
    { key: 'enrolled', label: 'Enrolled', align: 'right' },
    { key: 'capacity', label: 'Capacity', align: 'right' },
    { key: 'available', label: 'Available', align: 'right' },
    { key: 'fill', label: 'Fill Rate' },
  ]

  return (
    <PageShell>
      <PageHeader
        icon={Gauge}
        title="Section Capacity"
        subtitle="Monitor seat utilisation across every section — spot full, over-capacity, and growing programs at a glance"
      />

      {/* Summary cards */}
      {allRows.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <SummaryCard label="Total Sections"        value={stats.sections} color="#0F172A" />
          <SummaryCard label="Total Seats"           value={stats.seats}    color="#111827" />
          <SummaryCard label="Total Students"        value={stats.students} color="#111827" />
          <SummaryCard label="Near Full Sections"    value={stats.nearFull} color="#D97706" />
          <SummaryCard label="Full Sections"         value={stats.full}     color="#DC2626" />
          <SummaryCard label="Over Capacity"         value={stats.over}     color="#991B1B" />
        </div>
      )}

      {/* Filters + sort */}
      <div className="flex flex-wrap items-center gap-3">
        <FilterSelect value={school}     onChange={v => { setSchool(v); setDepartment(''); setProgram(''); setBatch('') }} options={opts.school}     allLabel="All schools" />
        <FilterSelect value={department} onChange={v => { setDepartment(v); setProgram(''); setBatch('') }}                options={opts.department} allLabel="All departments" />
        <FilterSelect value={program}    onChange={v => { setProgram(v); setBatch('') }}                                   options={opts.program}    allLabel="All programs" />
        <FilterSelect value={batch}      onChange={setBatch}                                                               options={opts.batch}      allLabel="All batches" width="w-[150px]" />
        <FilterSelect value={semester}   onChange={setSemester}                                                            options={opts.semester}   allLabel="All semesters" width="w-[150px]" />
        {anyFilter && (
          <button onClick={clearFilters} className="text-xs font-medium hover:underline" style={{ color: '#4B5563' }}>
            Clear filters
          </button>
        )}

        <div className="ml-auto flex items-center gap-2">
          <ArrowUpDown size={14} style={{ color: '#6B7280' }} />
          <Select value={sortKey} onValueChange={v => setSortKey(v as SortKey)}>
            <SelectTrigger className="w-[150px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="fill">Fill Rate</SelectItem>
              <SelectItem value="capacity">Capacity</SelectItem>
              <SelectItem value="enrollment">Enrollment</SelectItem>
            </SelectContent>
          </Select>
          <button
            onClick={() => setSortDir(d => d === 'desc' ? 'asc' : 'desc')}
            className="px-2.5 py-2 rounded-lg text-xs font-medium bg-white border border-gray-300"
            style={{ color: '#374151' }}
          >
            {sortDir === 'desc' ? 'High → Low' : 'Low → High'}
          </button>
        </div>
      </div>

      {canEdit && (
        <p className="text-xs" style={{ color: '#4B5563' }}>
          Click the pencil icon in the Capacity column to set or adjust a section's seat limit.
        </p>
      )}

      {/* Table */}
      {isLoading ? (
        <PageLoading message="Loading capacity data…" />
      ) : allRows.length === 0 ? (
        <div className="py-16 text-center">
          <Gauge className="h-10 w-10 mx-auto mb-3" style={{ color: '#9CA3AF' }} />
          <p className="text-sm" style={{ color: '#4B5563' }}>No sections found.</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm" style={{ color: '#4B5563' }}>No sections match your filters.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left" style={{ background: '#F9FAFB' }}>
                {HEAD.map(h => (
                  <th key={h.key}
                    className={`px-3 py-3 text-xs font-semibold uppercase tracking-wide ${h.align === 'right' ? 'text-right' : ''}`}
                    style={{ color: '#374151' }}>
                    {h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.section_id} className="border-b border-gray-100 last:border-0 hover:bg-gray-50">
                  <td className="px-3 py-3"><StatusIcon status={row.status} /></td>
                  <td className="px-3 py-3" style={{ color: '#111827' }}>{row.school_name ?? '—'}</td>
                  <td className="px-3 py-3" style={{ color: '#374151' }}>{row.department_name ?? '—'}</td>
                  <td className="px-3 py-3 font-medium" style={{ color: '#111827' }}>
                    {row.program_name ?? '—'}
                    {row.program_code && <span className="ml-1 text-xs" style={{ color: '#4B5563' }}>({row.program_code})</span>}
                  </td>
                  <td className="px-3 py-3" style={{ color: '#374151' }}>{row.batch_name ?? '—'}</td>
                  <td className="px-3 py-3 tabular-nums" style={{ color: '#374151' }}>{row.semester_number ?? '—'}</td>
                  <td className="px-3 py-3 font-semibold" style={{ color: '#0F172A' }}>{row.section_name}</td>
                  <td className="px-3 py-3 text-right tabular-nums font-semibold" style={{ color: '#111827' }}>{row.enrolled}</td>
                  <td className="px-3 py-3 text-right">
                    <div className="flex justify-end">
                      <CapacityCell
                        row={row} canEdit={canEdit}
                        onSave={(sid, val) => setMut.mutate({ sectionId: sid, val })}
                        isSaving={saving === row.section_id}
                      />
                    </div>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums font-semibold"
                    style={{ color: row.available == null ? '#9CA3AF' : row.available < 0 ? '#991B1B' : row.is_full ? '#DC2626' : '#111827' }}>
                    {row.available == null ? '—' : row.available}
                  </td>
                  <td className="px-3 py-3 min-w-[150px]"><FillBar pct={row.fill_pct} status={row.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Showing count */}
      {rows.length > 0 && (
        <p className="text-xs" style={{ color: '#4B5563' }}>
          Showing {rows.length} of {allRows.length} section{allRows.length !== 1 ? 's' : ''}
        </p>
      )}
    </PageShell>
  )
}
