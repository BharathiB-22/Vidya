import { useEffect, useState } from 'react'
import { School2, Plus } from 'lucide-react'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { sisApi, School } from '@/lib/api/sis'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'
import { useCurrentUser } from '@/hooks/useCurrentUser'

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateSchoolDialog({ open, onClose, onCreated }: {
  open: boolean
  onClose: () => void
  onCreated: (s: School) => void
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
      const s = await sisApi.createSchool({ name: name.trim(), code: code.trim(), description: desc.trim() || undefined })
      addToast('School created.', 'success')
      onCreated(s); reset(); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add school</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">School name</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="School of Computing" required />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Code <span className="text-gray-400 font-normal">(auto-uppercased, max 10 chars)</span></label>
            <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="SOC" maxLength={10} required />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Description <span className="text-gray-400 font-normal">(optional)</span></label>
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

function EditSchoolDialog({ school, onClose, onUpdated }: {
  school: School | null
  onClose: () => void
  onUpdated: (s: School) => void
}) {
  const [name,     setName]     = useState('')
  const [code,     setCode]     = useState('')
  const [desc,     setDesc]     = useState('')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (school) {
      setName(school.name)
      setCode(school.code)
      setDesc(school.description ?? '')
      setIsActive(school.is_active)
      setErr('')
    }
  }, [school])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!school) return
    setErr(''); setBusy(true)
    try {
      const updated = await sisApi.updateSchool(school.id, {
        name: name.trim(), code: code.trim(), description: desc.trim() || undefined, is_active: isActive,
      })
      addToast('School updated.', 'success')
      onUpdated(updated); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!school} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit school</DialogTitle></DialogHeader>
        {school && (
          <form onSubmit={submit} className="space-y-3 mt-2">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">School name</label>
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
              <input
                type="checkbox"
                id="school-active"
                checked={isActive}
                onChange={e => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
              <label htmlFor="school-active" className="text-sm font-medium text-gray-700">Active</label>
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
// Delete confirmation dialog
// ---------------------------------------------------------------------------

function DeleteSchoolDialog({ school, onClose, onDeleted }: {
  school: School | null
  onClose: () => void
  onDeleted: (id: string) => void
}) {
  const [err,  setErr]  = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { if (!school) setErr('') }, [school])

  async function confirm() {
    if (!school) return
    setErr(''); setBusy(true)
    try {
      await sisApi.deleteSchool(school.id)
      addToast('School deleted.', 'success')
      onDeleted(school.id); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!school} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Delete school</DialogTitle></DialogHeader>
        {school && (
          <div className="space-y-3 mt-2">
            <p className="text-sm text-gray-700">
              Delete <span className="font-semibold">{school.name}</span>? This cannot be undone.
              Schools with linked departments cannot be deleted.
            </p>
            {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="button" variant="destructive" onClick={confirm} disabled={busy}>
                {busy ? 'Deleting…' : 'Delete'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SchoolsPage() {
  const user = useCurrentUser()
  const role = user?.role ?? ''
  const canWrite = ['ADMIN', 'DEAN'].includes(role)

  const [schools,    setSchools]    = useState<School[]>([])
  const [loading,    setLoading]    = useState(true)
  const [err,        setErr]        = useState('')
  const [showAll,    setShowAll]    = useState(false)
  const [search,     setSearch]     = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<School | null>(null)
  const [deleting,   setDeleting]   = useState<School | null>(null)

  function load() {
    setLoading(true)
    sisApi.listSchools(showAll)
      .then(setSchools)
      .catch(e => setErr(getErrorMessage(e)))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [showAll]) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = schools.filter(s =>
    !search ||
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    s.code.toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <PageLoading />

  if (err) return (
    <PageShell>
      <PageHeader icon={School2} title="Schools" subtitle="Could not load schools" />
      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-start gap-3">
        <span className="shrink-0 mt-0.5">⚠</span>
        <div>
          <p className="font-medium">Failed to load schools</p>
          <p className="mt-0.5 text-red-600">{err}</p>
          <button onClick={load} className="mt-2 text-red-700 underline font-medium hover:text-red-900">
            Try again
          </button>
        </div>
      </div>
    </PageShell>
  )

  return (
    <PageShell>
      <PageHeader
        icon={School2}
        title="Schools"
        subtitle={`${schools.length} school${schools.length !== 1 ? 's' : ''}`}
        action={canWrite ? <Button onClick={() => setShowCreate(true)}>Add school</Button> : undefined}
      />

      <div className="flex gap-2 flex-wrap items-center">
        <Input
          className="w-48"
          placeholder="Search name or code…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <label className="flex items-center gap-1.5 text-sm text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={showAll}
            onChange={e => setShowAll(e.target.checked)}
            className="h-3.5 w-3.5 rounded"
          />
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
              {canWrite && <th className="px-4 py-2.5" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 5 : 4} className="py-2">
                  {schools.length === 0 ? (
                    <PageEmpty
                      icon={School2}
                      title="No schools added yet"
                      message="Schools are the top level of your academic hierarchy."
                      description="Create your first school to begin organising departments, programs, and faculty."
                      action={canWrite ? (
                        <Button size="sm" onClick={() => setShowCreate(true)}>
                          <Plus className="h-3.5 w-3.5 mr-1.5" />Add School
                        </Button>
                      ) : undefined}
                    />
                  ) : (
                    <PageEmpty message="No schools match your search." />
                  )}
                </td>
              </tr>
            ) : filtered.map(s => (
              <tr key={s.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{s.name}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-gray-100 text-gray-700">
                    {s.code}
                  </span>
                </td>
                <td className="px-4 py-3 text-gray-500 hidden md:table-cell">{s.description ?? '—'}</td>
                <td className="px-4 py-3">
                  {s.is_active
                    ? <span className="text-green-700 font-medium">Active</span>
                    : <span className="text-gray-400">Inactive</span>}
                </td>
                {canWrite && (
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button size="sm" variant="outline" onClick={() => setEditing(s)}>Edit</Button>
                      <Button size="sm" variant="outline" className="text-red-600 hover:text-red-700" onClick={() => setDeleting(s)}>Delete</Button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <CreateSchoolDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={s => setSchools(prev => [s, ...prev])}
      />
      <EditSchoolDialog
        school={editing}
        onClose={() => setEditing(null)}
        onUpdated={updated => setSchools(prev => prev.map(s => s.id === updated.id ? updated : s))}
      />
      <DeleteSchoolDialog
        school={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={id => setSchools(prev => prev.filter(s => s.id !== id))}
      />
    </PageShell>
  )
}
