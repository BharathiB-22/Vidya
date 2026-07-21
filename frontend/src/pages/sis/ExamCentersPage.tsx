import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { MapPin, Plus, Pencil } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { ExamCenterOut } from '@/lib/api/sis'

type FormState = { center_code: string; center_name: string; address: string; capacity: string }

const EMPTY: FormState = { center_code: '', center_name: '', address: '', capacity: '' }

function CenterModal({
  initial, onClose, onSaved,
}: { initial: ExamCenterOut | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<FormState>(
    initial
      ? {
          center_code: initial.center_code,
          center_name: initial.center_name,
          address: initial.address ?? '',
          capacity: initial.capacity != null ? String(initial.capacity) : '',
        }
      : EMPTY
  )
  const [error, setError] = useState<string | null>(null)

  const set = (k: keyof FormState, v: string) => setForm(f => ({ ...f, [k]: v }))

  const upsert = useMutation({
    mutationFn: () => {
      if (initial) {
        return sisApi.updateExamCenter(initial.id, {
          center_name: form.center_name,
          address: form.address || undefined,
          capacity: form.capacity ? parseInt(form.capacity) : undefined,
        })
      }
      return sisApi.createExamCenter({
        center_code: form.center_code,
        center_name: form.center_name,
        address: form.address || undefined,
        capacity: form.capacity ? parseInt(form.capacity) : undefined,
      })
    },
    onSuccess: () => { onSaved(); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Save failed'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[440px] rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
        <h3 className="text-base font-bold text-white mb-4">
          {initial ? 'Edit Center' : 'New Exam Center'}
        </h3>

        <div className="space-y-3">
          {!initial && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">Center Code</label>
              <input type="text" value={form.center_code} onChange={e => set('center_code', e.target.value)}
                placeholder="HALL-A"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 font-mono" />
            </div>
          )}
          <div>
            <label className="block text-xs text-slate-400 mb-1">Center Name</label>
            <input type="text" value={form.center_name} onChange={e => set('center_name', e.target.value)}
              placeholder="Main Campus Hall A"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Address (optional)</label>
            <input type="text" value={form.address} onChange={e => set('address', e.target.value)}
              placeholder="Block A, Ground Floor"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Capacity (optional)</label>
            <input type="number" min={1} value={form.capacity} onChange={e => set('capacity', e.target.value)}
              placeholder="200"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => upsert.mutate()}
            disabled={upsert.isPending || !form.center_name || (!initial && !form.center_code)}>
            {upsert.isPending ? 'Saving…' : initial ? 'Update' : 'Create'}
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function ExamCentersPage() {
  const qc = useQueryClient()
  const [modal, setModal] = useState<ExamCenterOut | null | 'new'>(null)

  const centersQ = useQuery({
    queryKey: ['exam-centers'],
    queryFn: () => sisApi.listExamCenters(),
  })

  const centers = centersQ.data ?? []
  const saved = () => qc.invalidateQueries({ queryKey: ['exam-centers'] })

  return (
    <PageShell>
      <PageHeader
        title="Exam Centers"
        icon={MapPin}
        action={
          <Button size="sm" onClick={() => setModal('new')}>
            <Plus size={14} className="mr-1" /> Add Center
          </Button>
        }
      />

      <div className="px-6 py-6 max-w-2xl">
        {centersQ.isLoading && <p className="text-sm text-slate-700">Loading…</p>}

        {centers.length === 0 && !centersQ.isLoading && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-700">
            <MapPin size={36} className="mb-3 opacity-30" />
            <p className="text-sm">No exam centers defined yet.</p>
          </div>
        )}

        <div className="space-y-2">
          {centers.map(c => (
            <div key={c.id}
              className="flex items-start gap-3 rounded-xl border border-white/8 bg-white/4 px-4 py-3">
              <MapPin size={16} className="text-blue-400 mt-0.5 flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-bold text-white">{c.center_name}</p>
                  <span className="text-[10px] font-mono text-slate-700 bg-white/5 px-1.5 py-0.5 rounded">
                    {c.center_code}
                  </span>
                </div>
                {c.address && <p className="text-xs text-slate-800 mt-0.5">{c.address}</p>}
                {c.capacity != null && (
                  <p className="text-xs text-slate-700 mt-0.5">Capacity: {c.capacity}</p>
                )}
              </div>
              <button onClick={() => setModal(c)}
                className="text-slate-700 hover:text-blue-400 transition-colors flex-shrink-0">
                <Pencil size={13} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {modal !== null && (
        <CenterModal
          initial={modal === 'new' ? null : modal}
          onClose={() => setModal(null)}
          onSaved={saved}
        />
      )}
    </PageShell>
  )
}
