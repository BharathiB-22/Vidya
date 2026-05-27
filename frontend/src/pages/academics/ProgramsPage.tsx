import { useEffect, useState } from 'react'
import { GraduationCap } from 'lucide-react'
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
import { academicsApi, AcadProgram, Department } from '@/lib/api/academics'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'

const DEGREE_TYPES = ['UG', 'PG', 'PHD', 'DIPLOMA', 'CERTIFICATE'] as const
type DegreeType = typeof DEGREE_TYPES[number]

const DEGREE_COLORS: Record<string, string> = {
  UG:          'bg-blue-100 text-blue-800',
  PG:          'bg-purple-100 text-purple-800',
  PHD:         'bg-indigo-100 text-indigo-800',
  DIPLOMA:     'bg-amber-100 text-amber-800',
  CERTIFICATE: 'bg-teal-100 text-teal-800',
}

const DEGREE_LABELS: Record<string, string> = {
  UG:          "UG (Bachelor's)",
  PG:          "PG (Master's)",
  PHD:         'PhD',
  DIPLOMA:     'Diploma',
  CERTIFICATE: 'Certificate',
}

function DegreeBadge({ type }: { type: string }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${DEGREE_COLORS[type] ?? 'bg-gray-100 text-gray-700'}`}>
      {DEGREE_LABELS[type] ?? type}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

function CreateProgramDialog({ open, onClose, onCreated, departments }: {
  open: boolean
  onClose: () => void
  onCreated: (p: AcadProgram) => void
  departments: Department[]
}) {
  const [deptId,    setDeptId]    = useState('')
  const [name,      setName]      = useState('')
  const [code,      setCode]      = useState('')
  const [degType,   setDegType]   = useState<DegreeType>('UG')
  const [duration,  setDuration]  = useState('4')
  const [err,       setErr]       = useState('')
  const [busy,      setBusy]      = useState(false)

  function reset() { setDeptId(''); setName(''); setCode(''); setDegType('UG'); setDuration('4'); setErr('') }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!deptId) { setErr('Please select a department.'); return }
    setErr(''); setBusy(true)
    try {
      const p = await academicsApi.createProgram({
        department_id: deptId, name: name.trim(), code: code.trim(),
        degree_type: degType, duration_years: Number(duration),
      })
      addToast('Program created.', 'success')
      onCreated(p); reset(); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add program</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3 mt-2">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Department</label>
            <Select value={deptId} onValueChange={setDeptId}>
              <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
              <SelectContent>
                {departments.filter(d => d.is_active).map(d => (
                  <SelectItem key={d.id} value={d.id}>{d.name} ({d.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Program name</label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="B.Tech Computer Science" required />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Code <span className="text-gray-400 font-normal">(auto-uppercased)</span></label>
              <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="BTCSE" maxLength={10} required />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Duration (years)</label>
              <Select value={duration} onValueChange={setDuration}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[1,2,3,4,5,6].map(n => <SelectItem key={n} value={String(n)}>{n} year{n > 1 ? 's' : ''}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Degree type</label>
            <Select value={degType} onValueChange={v => setDegType(v as DegreeType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {DEGREE_TYPES.map(t => <SelectItem key={t} value={t}>{DEGREE_LABELS[t]}</SelectItem>)}
              </SelectContent>
            </Select>
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

function EditProgramDialog({ prog, onClose, onUpdated }: {
  prog: AcadProgram | null
  onClose: () => void
  onUpdated: (p: AcadProgram) => void
}) {
  const [name,     setName]     = useState('')
  const [code,     setCode]     = useState('')
  const [degType,  setDegType]  = useState<DegreeType>('UG')
  const [duration, setDuration] = useState('4')
  const [isActive, setIsActive] = useState(true)
  const [err,      setErr]      = useState('')
  const [busy,     setBusy]     = useState(false)

  useEffect(() => {
    if (prog) {
      setName(prog.name); setCode(prog.code)
      setDegType(prog.degree_type as DegreeType)
      setDuration(String(prog.duration_years))
      setIsActive(prog.is_active); setErr('')
    }
  }, [prog])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!prog) return
    setErr(''); setBusy(true)
    try {
      const updated = await academicsApi.updateProgram(prog.id, {
        name: name.trim(), code: code.trim(), degree_type: degType,
        duration_years: Number(duration), is_active: isActive,
      })
      addToast('Program updated.', 'success')
      onUpdated(updated); onClose()
    } catch (e) { setErr(getErrorMessage(e)) }
    finally { setBusy(false) }
  }

  return (
    <Dialog open={!!prog} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit program</DialogTitle></DialogHeader>
        {prog && (
          <form onSubmit={submit} className="space-y-3 mt-2">
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Program name</label>
              <Input value={name} onChange={e => setName(e.target.value)} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">Code</label>
                <Input value={code} onChange={e => setCode(e.target.value.toUpperCase())} maxLength={10} required />
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium text-gray-700">Duration (years)</label>
                <Select value={duration} onValueChange={setDuration}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {[1,2,3,4,5,6].map(n => <SelectItem key={n} value={String(n)}>{n} year{n > 1 ? 's' : ''}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Degree type</label>
              <Select value={degType} onValueChange={v => setDegType(v as DegreeType)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {DEGREE_TYPES.map(t => <SelectItem key={t} value={t}>{DEGREE_LABELS[t]}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="prog-active" checked={isActive} onChange={e => setIsActive(e.target.checked)} className="h-4 w-4 rounded border-gray-300 text-indigo-600" />
              <label htmlFor="prog-active" className="text-sm font-medium text-gray-700">Active</label>
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

export default function ProgramsPage() {
  const [programs,  setPrograms]  = useState<AcadProgram[]>([])
  const [depts,     setDepts]     = useState<Department[]>([])
  const [filterDept, setFilterDept] = useState('ALL')
  const [showAll,   setShowAll]   = useState(false)
  const [loading,   setLoading]   = useState(true)
  const [err,       setErr]       = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editing,    setEditing]    = useState<AcadProgram | null>(null)

  useEffect(() => {
    academicsApi.listDepartments(true).then(setDepts).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    const deptId = filterDept === 'ALL' ? undefined : filterDept
    academicsApi.listPrograms(deptId, showAll)
      .then(setPrograms)
      .catch(e => setErr(getErrorMessage(e)))
      .finally(() => setLoading(false))
  }, [filterDept, showAll])

  const deptMap = Object.fromEntries(depts.map(d => [d.id, d]))

  if (loading) return <PageLoading />

  return (
    <PageShell>
      <PageHeader
        icon={GraduationCap}
        title="Programs"
        subtitle={`${programs.length} program${programs.length !== 1 ? 's' : ''}`}
        action={<Button onClick={() => setShowCreate(true)}>Add program</Button>}
      />

      {err && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{err}</p>}

      <div className="flex gap-2 flex-wrap items-center">
        <Select value={filterDept} onValueChange={setFilterDept}>
          <SelectTrigger className="w-52"><SelectValue placeholder="All departments" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All departments</SelectItem>
            {depts.filter(d => d.is_active).map(d => (
              <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
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
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Code</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Department</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Degree</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Duration</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {programs.length === 0 ? (
              <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">No programs yet.</td></tr>
            ) : programs.map(p => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-3 font-medium text-gray-900">{p.name}</td>
                <td className="px-4 py-3"><span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-semibold bg-gray-100 text-gray-700">{p.code}</span></td>
                <td className="px-4 py-3 text-gray-500 hidden lg:table-cell">{deptMap[p.department_id]?.name ?? '—'}</td>
                <td className="px-4 py-3"><DegreeBadge type={p.degree_type} /></td>
                <td className="px-4 py-3 text-gray-600">{p.duration_years} yr</td>
                <td className="px-4 py-3">
                  {p.is_active ? <span className="text-green-700 font-medium">Active</span> : <span className="text-gray-400">Inactive</span>}
                </td>
                <td className="px-4 py-3 text-right">
                  <Button size="sm" variant="outline" onClick={() => setEditing(p)}>Edit</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <CreateProgramDialog
        open={showCreate} onClose={() => setShowCreate(false)}
        departments={depts}
        onCreated={p => setPrograms(prev => [p, ...prev])}
      />
      <EditProgramDialog
        prog={editing} onClose={() => setEditing(null)}
        onUpdated={updated => setPrograms(prev => prev.map(p => p.id === updated.id ? updated : p))}
      />
    </PageShell>
  )
}
