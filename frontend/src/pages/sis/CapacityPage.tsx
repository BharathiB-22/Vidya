import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Gauge, AlertTriangle, CheckCircle, XCircle, Edit2, X, Check } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi } from '@/lib/api/sis'
import type { SectionCapacityOut } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'
import { useAuth } from '@/lib/auth'
import { addToast } from '@/hooks/useToast'
import { getErrorMessage } from '@/lib/api'

// ---------------------------------------------------------------------------
// Fill-rate bar + status
// ---------------------------------------------------------------------------

function FillBar({ pct, isFull }: { pct: number | null; isFull: boolean }) {
  if (pct === null) {
    return <span className="text-xs text-slate-600 italic">No cap set</span>
  }
  const clamped = Math.min(pct, 100)
  const color = isFull ? '#ef4444' : clamped >= 75 ? '#f59e0b' : '#10b981'
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${clamped}%`, background: color }} />
      </div>
      <span className="text-xs tabular-nums w-10 text-right" style={{ color }}>{pct}%</span>
    </div>
  )
}

function StatusIcon({ row }: { row: SectionCapacityOut }) {
  if (row.max_strength === null) return <Gauge size={15} className="text-slate-600" />
  if (row.is_full)   return <XCircle size={15} style={{ color: '#ef4444' }} />
  if ((row.fill_pct ?? 0) >= 75) return <AlertTriangle size={15} style={{ color: '#f59e0b' }} />
  return <CheckCircle size={15} style={{ color: '#10b981' }} />
}

// ---------------------------------------------------------------------------
// Inline capacity editor cell
// ---------------------------------------------------------------------------

function CapacityCell({
  row,
  canEdit,
  onSave,
  isSaving,
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
          type="number"
          min={1}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') commit(); if (e.key === 'Escape') setEditing(false) }}
          autoFocus
          className="w-20 px-2 py-1 text-xs rounded bg-white/5 border border-indigo-500 text-slate-200"
          placeholder="e.g. 60"
        />
        <button onClick={commit} disabled={isSaving} className="text-emerald-400 hover:text-emerald-300">
          <Check size={14} />
        </button>
        <button onClick={() => setEditing(false)} className="text-slate-500 hover:text-slate-300">
          <X size={14} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-1.5 group/cap">
      <span className="text-sm text-slate-300 tabular-nums">
        {row.max_strength != null ? row.max_strength : <span className="text-slate-600 italic text-xs">—</span>}
      </span>
      {canEdit && (
        <button
          onClick={startEdit}
          className="opacity-0 group-hover/cap:opacity-100 transition-opacity text-slate-500 hover:text-slate-300"
        >
          <Edit2 size={12} />
        </button>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function CapacityPage() {
  const { user }    = useAuth()
  const queryClient = useQueryClient()
  const [semesterId, setSemesterId] = useState<string>('')
  const [saving, setSaving]         = useState<string | null>(null)

  const canEdit = user?.role === 'ADMIN'

  const { data, isLoading } = useQuery({
    queryKey: ['sis-capacity', semesterId],
    queryFn: () => sisApi.listSectionsCapacity(semesterId || undefined),
  })

  const { data: semesters } = useQuery({
    queryKey: ['acad-semesters'],
    queryFn: () => academicsApi.listSemesters(),
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

  const rows = data ?? []
  const fullCount = rows.filter(r => r.is_full).length
  const warnCount = rows.filter(r => !r.is_full && (r.fill_pct ?? 0) >= 75).length
  const nocapCount = rows.filter(r => r.max_strength === null).length

  return (
    <PageShell>
      <PageHeader
        icon={Gauge}
        title="Enrollment Capacity"
        subtitle="Monitor and manage section seat limits"
      />

      {/* Summary pills */}
      {rows.length > 0 && (
        <div className="flex flex-wrap gap-3">
          {[
            { label: 'Sections', value: rows.length, color: '#64748b' },
            { label: 'Full',     value: fullCount,   color: '#ef4444' },
            { label: 'Near full', value: warnCount,  color: '#f59e0b' },
            { label: 'No cap',   value: nocapCount,  color: '#475569' },
          ].map(p => (
            <div key={p.label} className="px-4 py-2 rounded-lg text-sm"
              style={{ background: `${p.color}18`, border: `1px solid ${p.color}30`, color: p.color }}>
              <span className="font-bold tabular-nums">{p.value}</span>
              <span className="ml-1.5 text-xs opacity-70">{p.label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Semester filter */}
      <div className="flex items-center gap-3">
        <select
          value={semesterId}
          onChange={e => setSemesterId(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm bg-white/5 border border-white/10 text-slate-300"
        >
          <option value="">All semesters</option>
          {(semesters ?? []).map(s => (
            <option key={s.id} value={s.id}>{s.label ?? `Semester ${s.number}`}</option>
          ))}
        </select>
        {canEdit && (
          <p className="text-xs text-slate-600">Click the pencil icon in the Capacity column to edit.</p>
        )}
      </div>

      {/* Table */}
      {isLoading ? (
        <PageLoading message="Loading capacity data…" />
      ) : rows.length === 0 ? (
        <div className="py-16 text-center">
          <Gauge className="h-10 w-10 text-slate-700 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No sections found.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/8">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/8 text-left">
                {['', 'Section', 'Enrolled', 'Capacity', 'Available', 'Fill Rate'].map(h => (
                  <th key={h} className="px-4 py-3 text-xs font-medium text-slate-500 uppercase tracking-wide">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={row.section_id}
                  className="border-b border-white/5 last:border-0"
                  style={{ background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}
                >
                  <td className="px-4 py-3">
                    <StatusIcon row={row} />
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-200">{row.section_name}</td>
                  <td className="px-4 py-3 tabular-nums text-slate-300">{row.enrolled}</td>
                  <td className="px-4 py-3">
                    <CapacityCell
                      row={row}
                      canEdit={canEdit}
                      onSave={(sid, val) => setMut.mutate({ sectionId: sid, val })}
                      isSaving={saving === row.section_id}
                    />
                  </td>
                  <td className="px-4 py-3 tabular-nums text-slate-400">
                    {row.available != null
                      ? <span style={{ color: row.is_full ? '#ef4444' : '#94a3b8' }}>{row.available}</span>
                      : <span className="text-slate-600">—</span>
                    }
                  </td>
                  <td className="px-4 py-3 min-w-[140px]">
                    <FillBar pct={row.fill_pct} isFull={row.is_full} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageShell>
  )
}
