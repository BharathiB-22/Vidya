import { useEffect, useState } from 'react'
import { CalendarDays } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { academicsApi, Semester, Batch, AcadProgram } from '@/lib/api/academics'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateSemesterDialog({ open, onClose, onCreated, batches }: {
  open: boolean
  onClose: () => void
  onCreated: (s: Semester) => void
  batches: Batch[]
}) {
  const [batchId, setBatchId] = useState('')
  const [number,  setNumber]  = useState('')
  const [label,   setLabel]   = useState('')
  const [err,     setErr]     = useState('')
  const [busy,    setBusy]    = useState(false)

  function reset() { setBatchId(''); setNumber(''); setLabel(''); setErr('') }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!batchId) { setErr('Please select a batch.'); return }
    const num = Number(number)
    if (!num || num < 1 || num > 12) { setErr('Semester number must be 1–12.'); return }
    setErr(''); setBusy(true)
    try {
      const s = await academicsApi.createSemester({
        batch_id: batchId,
        number: num,
        label: label.trim() || undefined,
      })
      addToast('Semester created.', 'success')
      onCreated(s); reset(); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add semester</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Batch</label>
            <Select value={batchId} onValueChange={setBatchId}>
              <SelectTrigger><SelectValue placeholder="Select batch" /></SelectTrigger>
              <SelectContent>
                {batches.filter(b => b.is_active).map(b => (
                  <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Semester number</label>
            <Input
              type="number" min={1} max={12} required
              value={number} onChange={e => setNumber(e.target.value)}
              placeholder="e.g. 1"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Label <span className="text-gray-400 font-normal">(optional)</span></label>
            <Input
              value={label} onChange={e => setLabel(e.target.value)}
              placeholder="e.g. Odd Sem 2024"
            />
          </div>
          {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => { reset(); onClose() }}>Cancel</Button>
            <Button type="submit" disabled={busy}>{busy ? 'Creating…' : 'Create'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Edit dialog
// ---------------------------------------------------------------------------

function EditSemesterDialog({ semester, onClose, onUpdated }: {
  semester: Semester | null
  onClose: () => void
  onUpdated: (s: Semester) => void
}) {
  const [label,    setLabel]    = useState('')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (semester) { setLabel(semester.label ?? ''); setIsActive(semester.is_active); setErr('') }
  }, [semester])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!semester) return
    setErr(''); setBusy(true)
    try {
      const updated = await academicsApi.updateSemester(semester.id, {
        label: label.trim() || null,
        is_active: isActive,
      })
      addToast('Semester updated.', 'success')
      onUpdated(updated); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!semester} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Edit semester {semester ? `— Sem ${semester.number}` : ''}
          </DialogTitle>
        </DialogHeader>
        {semester && (
          <form onSubmit={submit} className="space-y-3 mt-2">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Label <span className="text-gray-400 font-normal">(optional)</span></label>
              <Input
                value={label} onChange={e => setLabel(e.target.value)}
                placeholder="e.g. Odd Sem 2024"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox" id="sem-active"
                checked={isActive} onChange={e => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
              <label htmlFor="sem-active" className="text-sm font-medium text-gray-700">Active</label>
            </div>
            {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SemestersPage() {
  const [semesters,  setSemesters]  = useState<Semester[]>([])
  const [batches,    setBatches]    = useState<Batch[]>([])
  const [programs,   setPrograms]   = useState<AcadProgram[]>([])
  const [filterProg, setFilterProg] = useState('ALL')
  const [filterBatch, setFilterBatch] = useState('ALL')
  const [showAll,    setShowAll]    = useState(false)
  const [loading,    setLoading]    = useState(true)
  const [err,        setErr]        = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<Semester | null>(null)

  useEffect(() => {
    academicsApi.listPrograms(undefined, true).then(setPrograms).catch(() => {})
    academicsApi.listBatches(undefined, true).then(setBatches).catch(() => {})
  }, [])

  const visibleBatches = filterProg === 'ALL'
    ? batches
    : batches.filter(b => b.program_id === filterProg)

  useEffect(() => {
    if (filterProg !== 'ALL' && filterBatch !== 'ALL') {
      const still = visibleBatches.find(b => b.id === filterBatch)
      if (!still) setFilterBatch('ALL')
    }
  }, [filterProg]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setLoading(true)
    const bid = filterBatch === 'ALL' ? undefined : filterBatch
    academicsApi.listSemesters(bid, showAll)
      .then(rows => setSemesters(rows.sort((a, b) => a.number - b.number)))
      .catch(e => setErr(getErrorMessage(e)))
      .finally(() => setLoading(false))
  }, [filterBatch, showAll])

  const batchMap = Object.fromEntries(batches.map(b => [b.id, b]))
  const progMap  = Object.fromEntries(programs.map(p => [p.id, p]))

  if (loading) return <PageLoading />

  return (
    <PageShell>
      <PageHeader
        icon={CalendarDays}
        title="Semesters"
        subtitle={`${semesters.length} semester${semesters.length !== 1 ? 's' : ''}`}
        action={<Button onClick={() => setShowCreate(true)}>Add semester</Button>}
      />

      {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}

      <div className="flex gap-2 flex-wrap items-center">
        <Select value={filterProg} onValueChange={v => { setFilterProg(v); setFilterBatch('ALL') }}>
          <SelectTrigger className="w-48"><SelectValue placeholder="All programs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All programs</SelectItem>
            {programs.filter(p => p.is_active).map(p => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={filterBatch} onValueChange={setFilterBatch}>
          <SelectTrigger className="w-48"><SelectValue placeholder="All batches" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All batches</SelectItem>
            {visibleBatches.filter(b => b.is_active).map(b => (
              <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} className="h-3.5 w-3.5 rounded" />
          Show inactive
        </label>
      </div>

      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Sem</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Label</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">Batch</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Program</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {semesters.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  No semesters found. Use <span className="font-medium">Batches → Generate Semesters</span> or add one manually.
                </td>
              </tr>
            ) : semesters.map(s => {
              const batch = batchMap[s.batch_id]
              const prog  = batch ? progMap[batch.program_id] : undefined
              return (
                <tr key={s.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-semibold text-gray-900">Sem {s.number}</td>
                  <td className="px-4 py-3 text-gray-600">{s.label ?? <span className="text-gray-300">—</span>}</td>
                  <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{batch?.name ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500 hidden lg:table-cell">
                    {prog?.name ?? '—'}
                    {prog && <span className="ml-1.5 text-xs text-gray-400">({prog.code})</span>}
                  </td>
                  <td className="px-4 py-3">
                    {s.is_active
                      ? <span className="text-green-700 font-medium">Active</span>
                      : <span className="text-gray-400">Inactive</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => setEditing(s)}>Edit</Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <CreateSemesterDialog
        open={showCreate} onClose={() => setShowCreate(false)}
        batches={batches}
        onCreated={s => setSemesters(prev => [...prev, s].sort((a, b) => a.number - b.number))}
      />
      <EditSemesterDialog
        semester={editing} onClose={() => setEditing(null)}
        onUpdated={updated => setSemesters(prev => prev.map(s => s.id === updated.id ? updated : s))}
      />
    </PageShell>
  )
}
