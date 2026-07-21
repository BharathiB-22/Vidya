import { useEffect, useState } from 'react'
import { Building2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { academicsApi, Department } from '@/lib/api/academics'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateDeptDialog({ open, onClose, onCreated }: {
  open: boolean
  onClose: () => void
  onCreated: (d: Department) => void
}) {
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [desc, setDesc] = useState('')
  const [err,  setErr]  = useState('')
  const [busy, setBusy] = useState(false)

  function reset() { setName(''); setCode(''); setDesc(''); setErr('') }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      const d = await academicsApi.createDepartment({ name: name.trim(), code: code.trim(), description: desc.trim() || undefined })
      addToast('Department created.', 'success')
      onCreated(d); reset(); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add department</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Department name</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Computer Science" required />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Code <span className="text-gray-600 font-normal">(auto-uppercased)</span></label>
            <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="CSE" maxLength={10} required />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Description <span className="text-gray-600 font-normal">(optional)</span></label>
            <Input value={desc} onChange={e => setDesc(e.target.value)} placeholder="Optional description" />
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

function EditDeptDialog({ dept, onClose, onUpdated }: {
  dept: Department | null
  onClose: () => void
  onUpdated: (d: Department) => void
}) {
  const [name,     setName]     = useState('')
  const [code,     setCode]     = useState('')
  const [desc,     setDesc]     = useState('')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (dept) { setName(dept.name); setCode(dept.code); setDesc(dept.description ?? ''); setIsActive(dept.is_active); setErr('') }
  }, [dept])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!dept) return
    setErr(''); setBusy(true)
    try {
      const updated = await academicsApi.updateDepartment(dept.id, {
        name: name.trim(), code: code.trim(), description: desc.trim() || undefined, is_active: isActive,
      })
      addToast('Department updated.', 'success')
      onUpdated(updated); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!dept} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit department</DialogTitle></DialogHeader>
        {dept && (
          <form onSubmit={submit} className="space-y-3 mt-2">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Department name</label>
              <Input value={name} onChange={e => setName(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Code</label>
              <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())} maxLength={10} required />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Description</label>
              <Input value={desc} onChange={e => setDesc(e.target.value)} />
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="dept-active" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-indigo-600" />
              <label htmlFor="dept-active" className="text-sm font-medium text-gray-700">Active</label>
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

export default function DepartmentsPage() {
  const [depts,   setDepts]   = useState<Department[]>([])
  const [loading, setLoading] = useState(true)
  const [err,     setErr]     = useState('')
  const [showAll, setShowAll] = useState(false)
  const [search,  setSearch]  = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<Department | null>(null)

  function load() {
    setLoading(true)
    academicsApi.listDepartments(showAll)
      .then(setDepts)
      .catch(e => setErr(getErrorMessage(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [showAll]) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = depts.filter(d =>
    !search || d.name.toLowerCase().includes(search.toLowerCase()) || d.code.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <PageLoading />

  return (
    <PageShell>
      <PageHeader
        icon={Building2}
        title="Departments"
        subtitle={`${depts.length} department${depts.length !== 1 ? 's' : ''}`}
        action={<Button onClick={() => setShowCreate(true)}>Add department</Button>}
      />

      {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}

      <div className="flex gap-2 flex-wrap items-center">
        <Input className="w-48" placeholder="Search name or code…" value={search} onChange={e => setSearch(e.target.value)} />
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
          <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} className="h-3.5 w-3.5 rounded" />
          Show inactive
        </label>
      </div>

      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Code</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">Description</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-600">
                {depts.length === 0 ? 'No departments yet.' : 'No departments match your search.'}
              </td></tr>
            ) : filtered.map(d => (
              <tr key={d.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{d.name}</td>
                <td className="px-4 py-3"><span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-gray-100 text-gray-700">{d.code}</span></td>
                <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{d.description ?? '—'}</td>
                <td className="px-4 py-3">
                  {d.is_active ? <span className="text-green-700 font-medium">Active</span> : <span className="text-gray-600">Inactive</span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <Button size="sm" variant="outline" onClick={() => setEditing(d)}>Edit</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <CreateDeptDialog open={showCreate} onClose={() => setShowCreate(false)} onCreated={d => setDepts(prev => [d, ...prev])} />
      <EditDeptDialog dept={editing} onClose={() => setEditing(null)} onUpdated={updated => setDepts(prev => prev.map(d => d.id === updated.id ? updated : d))} />
    </PageShell>
  )
}
