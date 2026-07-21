import { useEffect, useState } from 'react'
import { Layers, Plus } from 'lucide-react'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { academicsApi, Department } from '@/lib/api/academics'
import { sisApi, School } from '@/lib/api/sis'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'
import { useCurrentUser } from '@/hooks/useCurrentUser'

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateDeptDialog({ open, onClose, onCreated, schools }: {
  open: boolean
  onClose: () => void
  onCreated: (d: Department) => void
  schools: School[]
}) {
  const [name,     setName]     = useState('')
  const [code,     setCode]     = useState('')
  const [desc,     setDesc]     = useState('')
  const [schoolId, setSchoolId] = useState('')
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  function reset() { setName(''); setCode(''); setDesc(''); setSchoolId(''); setErr('') }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setErr(''); setBusy(true)
    try {
      const d = await academicsApi.createDepartment({
        name: name.trim(),
        code: code.trim(),
        description: desc.trim() || undefined,
        school_id: schoolId || undefined,
      })
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
            <label className="text-sm font-medium text-gray-700">School</label>
            <select
              value={schoolId}
              onChange={e => setSchoolId(e.target.value)}
              className="w-full border rounded-md px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="">— No school assigned —</option>
              {schools.map(s => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Department name</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="Computer Applications" required />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Code <span className="text-gray-600 font-normal">(auto-uppercased)</span></label>
            <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="MCA" maxLength={10} required />
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

function EditDeptDialog({ dept, onClose, onUpdated, schools }: {
  dept: Department | null
  onClose: () => void
  onUpdated: (d: Department) => void
  schools: School[]
}) {
  const [name,     setName]     = useState('')
  const [code,     setCode]     = useState('')
  const [desc,     setDesc]     = useState('')
  const [schoolId, setSchoolId] = useState('')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (dept) {
      setName(dept.name)
      setCode(dept.code)
      setDesc(dept.description ?? '')
      setSchoolId(dept.school_id ?? '')
      setIsActive(dept.is_active)
      setErr('')
    }
  }, [dept])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!dept) return
    setErr(''); setBusy(true)
    try {
      const updated = await academicsApi.updateDepartment(dept.id, {
        name: name.trim(),
        code: code.trim(),
        description: desc.trim() || undefined,
        school_id: schoolId || undefined,
        is_active: isActive,
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
              <label className="text-sm font-medium text-gray-700">School</label>
              <select
                value={schoolId}
                onChange={e => setSchoolId(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="">— No school assigned —</option>
                {schools.map(s => <option key={s.id} value={s.id}>{s.name} ({s.code})</option>)}
              </select>
            </div>
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
              <input
                type="checkbox"
                id="dept-active"
                checked={isActive}
                onChange={e => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
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

export default function SisDepartmentsPage() {
  const user = useCurrentUser()
  const role = user?.role ?? ''
  const canWrite = ['ADMIN', 'DEAN'].includes(role)

  const [depts,      setDepts]      = useState<Department[]>([])
  const [schools,    setSchools]    = useState<School[]>([])
  const [loading,    setLoading]    = useState(true)
  const [err,        setErr]        = useState('')
  const [showAll,    setShowAll]    = useState(false)
  const [search,     setSearch]     = useState('')
  const [schoolFilter, setSchoolFilter] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<Department | null>(null)

  function load() {
    setLoading(true)
    Promise.allSettled([
      academicsApi.listDepartments(showAll),
      sisApi.listSchools(true),
    ])
      .then(([deptsResult, schoolsResult]) => {
        if (deptsResult.status === 'fulfilled') {
          setDepts(deptsResult.value)
        } else {
          setErr(getErrorMessage(deptsResult.reason))
        }
        if (schoolsResult.status === 'fulfilled') {
          setSchools(schoolsResult.value)
        }
        // Schools failure is non-critical (used only for filter dropdown);
        // departments list is still shown.
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [showAll]) // eslint-disable-line react-hooks/exhaustive-deps

  const schoolMap = Object.fromEntries(schools.map(s => [s.id, s]))

  const filtered = depts.filter(d => {
    const matchesSearch = !search ||
      d.name.toLowerCase().includes(search.toLowerCase()) ||
      d.code.toLowerCase().includes(search.toLowerCase())
    const matchesSchool = !schoolFilter || d.school_id === schoolFilter
    return matchesSearch && matchesSchool
  })

  if (loading) return <PageLoading />

  if (err) return (
    <PageShell>
      <PageHeader icon={Layers} title="Departments" subtitle="Could not load departments" />
      <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700 flex items-start gap-3">
        <span className="shrink-0 mt-0.5">⚠</span>
        <div>
          <p className="font-medium">Failed to load departments</p>
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
        icon={Layers}
        title="Departments"
        subtitle={`${depts.length} department${depts.length !== 1 ? 's' : ''}`}
        action={canWrite ? <Button onClick={() => setShowCreate(true)}>Add department</Button> : undefined}
      />

      <div className="flex gap-2 flex-wrap items-center">
        <Input
          className="w-48"
          placeholder="Search name or code…"
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
        <select
          value={schoolFilter}
          onChange={e => setSchoolFilter(e.target.value)}
          className="border rounded-md px-3 py-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All schools</option>
          {schools.filter(s => s.is_active).map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
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
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">School</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              {canWrite && <th className="px-4 py-2.5" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={canWrite ? 5 : 4} className="py-2">
                  {depts.length === 0 ? (
                    <PageEmpty
                      icon={Layers}
                      title="No departments added yet"
                      message="Departments sit under a school and contain your degree programs."
                      description="Create your first department to begin building the academic structure."
                      action={canWrite ? (
                        <Button size="sm" onClick={() => setShowCreate(true)}>
                          <Plus className="h-3.5 w-3.5 mr-1.5" />Add Department
                        </Button>
                      ) : undefined}
                    />
                  ) : (
                    <PageEmpty message="No departments match your filter." />
                  )}
                </td>
              </tr>
            ) : filtered.map(d => {
              const school = d.school_id ? schoolMap[d.school_id] : null
              return (
                <tr key={d.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{d.name}</td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-gray-100 text-gray-700">
                      {d.code}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500 hidden md:table-cell">
                    {school
                      ? <span className="inline-flex items-center gap-1.5">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-blue-50 text-blue-700">{school.code}</span>
                          {school.name}
                        </span>
                      : <span className="text-gray-500 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {d.is_active
                      ? <span className="text-green-700 font-medium">Active</span>
                      : <span className="text-gray-600">Inactive</span>}
                  </td>
                  {canWrite && (
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="outline" onClick={() => setEditing(d)}>Edit</Button>
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <CreateDeptDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={d => setDepts(prev => [d, ...prev])}
        schools={schools.filter(s => s.is_active)}
      />
      <EditDeptDialog
        dept={editing}
        onClose={() => setEditing(null)}
        onUpdated={updated => setDepts(prev => prev.map(d => d.id === updated.id ? updated : d))}
        schools={schools.filter(s => s.is_active)}
      />
    </PageShell>
  )
}
