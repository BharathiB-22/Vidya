import { useEffect, useState } from 'react'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { Calendar, Wand2, Plus } from 'lucide-react'
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
import { academicsApi, Batch, AcadProgram } from '@/lib/api/academics'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateBatchDialog({ open, onClose, onCreated, programs }: {
  open: boolean
  onClose: () => void
  onCreated: (b: Batch) => void
  programs: AcadProgram[]
}) {
  const [progId,     setProgId]     = useState('')
  const [name,       setName]       = useState('')
  const [startYear,  setStartYear]  = useState('')
  const [endYear,    setEndYear]    = useState('')
  const [err,        setErr]        = useState('')
  const [busy,       setBusy]       = useState(false)

  const selectedProg = programs.find(p => p.id === progId)

  function handleStartYear(val: string) {
    setStartYear(val)
    if (val && selectedProg) {
      setEndYear(String(Number(val) + selectedProg.duration_years))
    }
  }

  function handleProg(id: string) {
    setProgId(id)
    if (startYear) {
      const prog = programs.find(p => p.id === id)
      if (prog) setEndYear(String(Number(startYear) + prog.duration_years))
    }
  }

  function reset() { setProgId(''); setName(''); setStartYear(''); setEndYear(''); setErr('') }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!progId) { setErr('Please select a program.'); return }
    setErr(''); setBusy(true)
    try {
      const b = await academicsApi.createBatch({
        program_id: progId, name: name.trim(),
        start_year: Number(startYear), end_year: Number(endYear),
      })
      addToast('Batch created.', 'success')
      onCreated(b); reset(); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add batch</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Program</label>
            <Select value={progId} onValueChange={handleProg}>
              <SelectTrigger><SelectValue placeholder="Select program" /></SelectTrigger>
              <SelectContent>
                {programs.filter(p => p.is_active).map(p => (
                  <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {selectedProg && (
              <p className="text-xs text-gray-400">{selectedProg.duration_years}-year program — end year auto-calculated</p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Batch name</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. 2023-2027" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Start year</label>
              <Input type="number" value={startYear} onChange={e => handleStartYear(e.target.value)} placeholder="2023" min={2000} max={2100} required />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">End year</label>
              <Input type="number" value={endYear} onChange={e => setEndYear(e.target.value)} placeholder="2027" min={2000} max={2100} required />
            </div>
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

function EditBatchDialog({ batch, onClose, onUpdated }: {
  batch: Batch | null
  onClose: () => void
  onUpdated: (b: Batch) => void
}) {
  const [name,     setName]     = useState('')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (batch) { setName(batch.name); setIsActive(batch.is_active); setErr('') }
  }, [batch])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!batch) return
    setErr(''); setBusy(true)
    try {
      const updated = await academicsApi.updateBatch(batch.id, { name: name.trim(), is_active: isActive })
      addToast('Batch updated.', 'success')
      onUpdated(updated); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!batch} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit batch</DialogTitle></DialogHeader>
        {batch && (
          <form onSubmit={submit} className="space-y-3 mt-2">
            <p className="text-xs text-gray-500">{batch.start_year} – {batch.end_year}</p>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Batch name</label>
              <Input value={name} onChange={e => setName(e.target.value)} required />
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="batch-active" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-indigo-600" />
              <label htmlFor="batch-active" className="text-sm font-medium text-gray-700">Active</label>
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

export default function BatchesPage() {
  const [batches,    setBatches]    = useState<Batch[]>([])
  const [programs,   setPrograms]   = useState<AcadProgram[]>([])
  const [filterProg, setFilterProg] = useState('ALL')
  const [showAll,    setShowAll]    = useState(false)
  const [loading,    setLoading]    = useState(true)
  const [err,        setErr]        = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<Batch | null>(null)
  const [generatingId, setGeneratingId] = useState<string | null>(null)

  useEffect(() => {
    academicsApi.listPrograms(undefined, true).then(setPrograms).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    const pid = filterProg === 'ALL' ? undefined : filterProg
    academicsApi.listBatches(pid, showAll)
      .then(setBatches)
      .catch(e => setErr(getErrorMessage(e)))
      .finally(() => setLoading(false))
  }, [filterProg, showAll])

  const progMap = Object.fromEntries(programs.map(p => [p.id, p]))

  async function handleGenerate(batchId: string) {
    setGeneratingId(batchId)
    try {
      const result = await academicsApi.generateSemesters(batchId)
      if (result.created > 0) {
        addToast(`Generated ${result.created} semester${result.created !== 1 ? 's' : ''}.`, 'success')
      } else {
        addToast(`All ${result.skipped} semesters already exist.`, 'success')
      }
    } catch (e) {
      addToast(getErrorMessage(e), 'error')
    } finally {
      setGeneratingId(null)
    }
  }

  if (loading) return <PageLoading />

  return (
    <PageShell>
      <PageHeader
        icon={Calendar}
        title="Academic Batches"
        subtitle={`${batches.length} batch${batches.length !== 1 ? 'es' : ''}`}
        action={<Button onClick={() => setShowCreate(true)}>Add batch</Button>}
      />

      {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}

      <div className="flex gap-2 flex-wrap items-center">
        <Select value={filterProg} onValueChange={setFilterProg}>
          <SelectTrigger className="w-56"><SelectValue placeholder="All programs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All programs</SelectItem>
            {programs.filter(p => p.is_active).map(p => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
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
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Batch</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Years</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Program</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-4 py-2.5 text-right text-xs font-semibold text-gray-500 uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {batches.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-2">
                  <PageEmpty
                    icon={Calendar}
                    title="No intake batches yet"
                    message="Batches represent an academic year intake for a degree program."
                    description="Create a batch to start assigning semesters and enrolling students."
                    action={
                      <Button size="sm" onClick={() => setShowCreate(true)}>
                        <Plus className="h-3.5 w-3.5 mr-1.5" />Add Batch
                      </Button>
                    }
                  />
                </td>
              </tr>
            ) : batches.map(b => (
              <tr key={b.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{b.name}</td>
                <td className="px-4 py-3 text-gray-600">{b.start_year} – {b.end_year}</td>
                <td className="px-4 py-3 text-gray-500 hidden lg:table-cell">
                  {progMap[b.program_id]?.name ?? '—'}
                  {progMap[b.program_id] && (
                    <span className="ml-1.5 text-xs text-gray-400">({progMap[b.program_id].code})</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {b.is_active ? <span className="text-green-700 font-medium">Active</span> : <span className="text-gray-400">Inactive</span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-1.5">
                    <Button
                      size="sm" variant="outline"
                      disabled={generatingId === b.id}
                      onClick={() => handleGenerate(b.id)}
                      title="Generate semesters for this batch"
                    >
                      <Wand2 className="h-3.5 w-3.5 mr-1" />
                      {generatingId === b.id ? 'Generating…' : 'Semesters'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setEditing(b)}>Edit</Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <CreateBatchDialog
        open={showCreate} onClose={() => setShowCreate(false)}
        programs={programs}
        onCreated={b => setBatches(prev => [b, ...prev])}
      />
      <EditBatchDialog
        batch={editing} onClose={() => setEditing(null)}
        onUpdated={updated => setBatches(prev => prev.map(b => b.id === updated.id ? updated : b))}
      />
    </PageShell>
  )
}
