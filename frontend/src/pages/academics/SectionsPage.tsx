import { useEffect, useState } from 'react'
import { LayoutList, Plus } from 'lucide-react'
import { PageEmpty } from '@/components/shared/PageEmpty'
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
import { academicsApi, AcadProgram, Batch, Section, Semester } from '@/lib/api/academics'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateSectionDialog({ open, onClose, onCreated, semesterId, semesterLabel }: {
  open: boolean
  onClose: () => void
  onCreated: (s: Section) => void
  semesterId: string
  semesterLabel: string
}) {
  const [name,      setName]      = useState('')
  const [maxStr,    setMaxStr]    = useState('')
  const [err,       setErr]       = useState('')
  const [busy,      setBusy]      = useState(false)

  function reset() { setName(''); setMaxStr(''); setErr('') }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      const s = await academicsApi.createSection({
        semester_id: semesterId,
        name: name.trim().toUpperCase(),
        ...(maxStr ? { max_strength: Number(maxStr) } : {}),
      })
      addToast('Section created.', 'success')
      onCreated(s); reset(); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add section</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <p className="text-xs text-gray-500">Adding to: <span className="font-medium text-gray-700">{semesterLabel}</span></p>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Section name <span className="text-gray-600 font-normal">(auto-uppercased)</span></label>
            <Input
              value={name}
              onChange={e => setName(e.target.value.toUpperCase())}
              placeholder="A"
              maxLength={10}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Max strength <span className="text-gray-600 font-normal">(optional)</span></label>
            <Input
              type="number"
              value={maxStr}
              onChange={e => setMaxStr(e.target.value)}
              placeholder="60"
              min={1}
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

function EditSectionDialog({ section, onClose, onUpdated }: {
  section: Section | null
  onClose: () => void
  onUpdated: (s: Section) => void
}) {
  const [name,     setName]     = useState('')
  const [maxStr,   setMaxStr]   = useState('')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (section) {
      setName(section.name)
      setMaxStr(section.max_strength != null ? String(section.max_strength) : '')
      setIsActive(section.is_active)
      setErr('')
    }
  }, [section])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!section) return
    setErr(''); setBusy(true)
    try {
      const updated = await academicsApi.updateSection(section.id, {
        name: name.trim().toUpperCase(),
        ...(maxStr ? { max_strength: Number(maxStr) } : {}),
        is_active: isActive,
      })
      addToast('Section updated.', 'success')
      onUpdated(updated); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!section} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit section</DialogTitle></DialogHeader>
        {section && (
          <form onSubmit={submit} className="space-y-3 mt-2">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Section name</label>
              <Input value={name} onChange={e => setName(e.target.value.toUpperCase())} maxLength={10} required />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Max strength <span className="text-gray-600 font-normal">(optional)</span></label>
              <Input type="number" value={maxStr} onChange={e => setMaxStr(e.target.value)} min={1} />
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="sec-active" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-indigo-600" />
              <label htmlFor="sec-active" className="text-sm font-medium text-gray-700">Active</label>
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

export default function SectionsPage() {
  const [programs,  setPrograms]  = useState<AcadProgram[]>([])
  const [batches,   setBatches]   = useState<Batch[]>([])
  const [semesters, setSemesters] = useState<Semester[]>([])
  const [sections,  setSections]  = useState<Section[]>([])

  const [filterProg, setFilterProg] = useState('NONE')
  const [filterBatch, setFilterBatch] = useState('NONE')
  const [filterSem, setFilterSem] = useState('NONE')

  const [showAll,    setShowAll]    = useState(false)
  const [loading,    setLoading]    = useState(false)
  const [err,        setErr]        = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<Section | null>(null)

  // Load programs once
  useEffect(() => {
    academicsApi.listPrograms(undefined, true).then(setPrograms).catch(() => {})
  }, [])

  // Load batches when program changes
  useEffect(() => {
    setBatches([]); setFilterBatch('NONE')
    setSemesters([]); setFilterSem('NONE')
    setSections([])
    if (filterProg !== 'NONE') {
      academicsApi.listBatches(filterProg, true).then(setBatches).catch(() => {})
    }
  }, [filterProg])

  // Load semesters when batch changes
  useEffect(() => {
    setSemesters([]); setFilterSem('NONE')
    setSections([])
    if (filterBatch !== 'NONE') {
      academicsApi.listSemesters(filterBatch, true).then(setSemesters).catch(() => {})
    }
  }, [filterBatch])

  // Load sections when semester changes
  useEffect(() => {
    setSections([])
    if (filterSem !== 'NONE') {
      setLoading(true)
      academicsApi.listSections(filterSem, showAll)
        .then(setSections)
        .catch(e => setErr(getErrorMessage(e)))
        .finally(() => setLoading(false))
    }
  }, [filterSem, showAll])

  const selectedSemester = semesters.find(s => s.id === filterSem)
  const semesterLabel = selectedSemester
    ? (selectedSemester.label ?? `Semester ${selectedSemester.number}`)
    : ''

  const canAdd = filterSem !== 'NONE'

  return (
    <PageShell>
      <PageHeader
        icon={LayoutList}
        title="Sections"
        subtitle={filterSem !== 'NONE' ? `${sections.length} section${sections.length !== 1 ? 's' : ''}` : 'Select a semester to view sections'}
        action={
          <Button onClick={() => setShowCreate(true)} disabled={!canAdd} title={!canAdd ? 'Select a semester first' : ''}>
            Add section
          </Button>
        }
      />

      {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}

      {/* Cascade filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <Select value={filterProg} onValueChange={setFilterProg}>
          <SelectTrigger className="w-52"><SelectValue placeholder="Select program" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="NONE">— Program —</SelectItem>
            {programs.filter(p => p.is_active).map(p => (
              <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterBatch} onValueChange={setFilterBatch} disabled={filterProg === 'NONE'}>
          <SelectTrigger className="w-44"><SelectValue placeholder="Select batch" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="NONE">— Batch —</SelectItem>
            {batches.filter(b => b.is_active).map(b => (
              <SelectItem key={b.id} value={b.id}>{b.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filterSem} onValueChange={setFilterSem} disabled={filterBatch === 'NONE'}>
          <SelectTrigger className="w-40"><SelectValue placeholder="Select semester" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="NONE">— Semester —</SelectItem>
            {semesters.filter(s => s.is_active).map(s => (
              <SelectItem key={s.id} value={s.id}>
                {s.label ?? `Semester ${s.number}`}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {filterSem !== 'NONE' && (
          <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} className="h-3.5 w-3.5 rounded" />
            Show inactive
          </label>
        )}
      </div>

      {/* Empty state when no semester selected */}
      {filterSem === 'NONE' && (
        <div className="border rounded-lg py-12 text-center text-gray-600 bg-gray-50">
          <LayoutList className="h-8 w-8 mx-auto mb-2 text-gray-500" />
          <p className="text-sm">Select a program → batch → semester to view sections.</p>
        </div>
      )}

      {/* Table */}
      {filterSem !== 'NONE' && (
        loading ? (
          <div className="py-8">
            <div className="flex items-center justify-center gap-2 text-gray-600 text-sm">
              <div className="h-5 w-5 animate-spin rounded-full border-4 border-gray-300 border-t-gray-500" />
              Loading…
            </div>
          </div>
        ) : (
          <div className="border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Section</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Max strength</th>
                  <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {sections.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="py-2">
                      <PageEmpty
                        icon={LayoutList}
                        title="No sections yet"
                        message="Sections define the class groups within a semester."
                        description="Add a section to start assigning students and faculty."
                        action={
                          <Button size="sm" onClick={() => setShowCreate(true)}>
                            <Plus className="h-3.5 w-3.5 mr-1.5" />Add Section
                          </Button>
                        }
                      />
                    </td>
                  </tr>
                ) : sections.map(s => (
                  <tr key={s.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-semibold text-gray-900">Section {s.name}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {s.max_strength != null ? `${s.max_strength} students` : '—'}
                    </td>
                    <td className="px-4 py-3">
                      {s.is_active ? <span className="text-green-700 font-medium">Active</span> : <span className="text-gray-600">Inactive</span>}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="outline" onClick={() => setEditing(s)}>Edit</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {canAdd && (
        <CreateSectionDialog
          open={showCreate}
          onClose={() => setShowCreate(false)}
          onCreated={s => setSections(prev => [...prev, s].sort((a, b) => a.name.localeCompare(b.name)))}
          semesterId={filterSem}
          semesterLabel={semesterLabel}
        />
      )}
      <EditSectionDialog
        section={editing}
        onClose={() => setEditing(null)}
        onUpdated={updated => setSections(prev => prev.map(s => s.id === updated.id ? updated : s))}
      />
    </PageShell>
  )
}
