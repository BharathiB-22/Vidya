import { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Users, UserPlus } from 'lucide-react'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { usersApi, UserRecord, CreateUserPayload, UpdateUserPayload } from '@/lib/api/users'
import { academicsApi, AcadProgram, Department } from '@/lib/api/academics'
import { getErrorMessage } from '@/lib/api'
import { addToast } from '@/hooks/useToast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

// Every role value that may appear on a user row — drives badge colors and the
// Role type. Legacy standalone GUIDE/EVALUATOR/BOARD accounts still exist, so
// their badges must continue to render.
const ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD', 'GUIDE', 'EVALUATOR'] as const
type Role = typeof ROLES[number]

// Roles offered in the filter dropdown. GUIDE / EVALUATOR are responsibilities
// (granted from the faculty profile via faculty_role_grants), never primary
// roles, so they are not offered as account filters. BOARD is retained for now
// pending the Phase 1.7 governance audit and because legacy standalone BOARD
// accounts may still exist and need to be located.
const FILTER_ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD'] as const

// Roles assignable as a PRIMARY account role. GUIDE / EVALUATOR are
// responsibilities (granted from the Faculty Profile via faculty_role_grants),
// not primary roles. BOARD is a primary role (leadership/governance accounts).
const PRIMARY_ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD'] as const

// Pre-Phase 1.7 users may have role=FACULTY + a BOARD or DEAN grant instead of
// the proper primary role.  Display the grant as the effective role so the Users
// page is consistent regardless of import vintage.
function displayRole(u: UserRecord): string {
  if (u.role === 'FACULTY' && u.grants?.includes('BOARD')) return 'BOARD'
  if (u.role === 'FACULTY' && u.grants?.includes('DEAN'))  return 'DEAN'
  return u.role
}

const ROLE_COLORS: Record<string, string> = {
  ADMIN:     'bg-indigo-100 text-indigo-800',
  DEAN:      'bg-purple-100 text-purple-800',
  FACULTY:   'bg-blue-100 text-blue-800',
  STUDENT:   'bg-green-100 text-green-800',
  BOARD:     'bg-amber-100 text-amber-800',
  GUIDE:     'bg-teal-100 text-teal-800',
  EVALUATOR: 'bg-orange-100 text-orange-800',
}

// ---------------------------------------------------------------------------
// UUID copy button
// ---------------------------------------------------------------------------

function CopyUuidButton({ uuid }: { uuid: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(uuid).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }, [uuid])

  return (
    <button
      type="button"
      onClick={handleCopy}
      title="Copy UUID"
      className="ml-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-mono text-gray-500 bg-gray-100 hover:bg-gray-200 transition-colors"
    >
      <span className="truncate max-w-[9rem]">{uuid}</span>
      <span className="shrink-0">{copied ? '✓' : '⎘'}</span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Program dropdown (shared by Create and Edit dialogs)
// ---------------------------------------------------------------------------

interface ProgramSelectProps {
  value: string
  onChange: (v: string) => void
  programs: AcadProgram[]
  required?: boolean
}

function ProgramSelect({ value, onChange, programs, required }: ProgramSelectProps) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-gray-700">
        Program {required && <span className="text-red-500">*</span>}
      </label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder="Select program…" />
        </SelectTrigger>
        <SelectContent>
          {programs.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.name} <span className="text-gray-400 text-xs">({p.code})</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Department dropdown (Faculty/Dean creation)
// ---------------------------------------------------------------------------

interface DepartmentSelectProps {
  value: string
  onChange: (v: string) => void
  departments: Department[]
  required?: boolean
}

function DepartmentSelect({ value, onChange, departments, required }: DepartmentSelectProps) {
  return (
    <div className="space-y-1">
      <label className="text-sm font-medium text-gray-700">
        Department {required && <span className="text-red-500">*</span>}
      </label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger>
          <SelectValue placeholder="Select department…" />
        </SelectTrigger>
        <SelectContent>
          {departments.map((d) => (
            <SelectItem key={d.id} value={d.id}>
              {d.name} <span className="text-gray-400 text-xs">({d.code})</span>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Create dialog
// ---------------------------------------------------------------------------

interface CreateDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (user: UserRecord) => void
  programs: AcadProgram[]
  departments: Department[]
}

function CreateUserDialog({ open, onClose, onCreated, programs, departments }: CreateDialogProps) {
  const [email,        setEmail]        = useState('')
  const [fullName,     setFullName]     = useState('')
  const [password,     setPassword]     = useState('')
  const [role,         setRole]         = useState<Role>('FACULTY')
  const [identifier,   setIdentifier]   = useState('')
  const [programId,    setProgramId]    = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [error,        setError]        = useState('')
  const [loading,      setLoading]      = useState(false)

  function reset() {
    setEmail(''); setFullName(''); setPassword(''); setRole('FACULTY')
    setIdentifier(''); setProgramId(''); setDepartmentId(''); setError('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (role === 'STUDENT' && !programId) {
      setError('Program is required for students.')
      return
    }
    if ((role === 'FACULTY' || role === 'DEAN') && !departmentId) {
      setError('Department is required for Faculty and Dean accounts.')
      return
    }
    setLoading(true)
    try {
      const payload: CreateUserPayload = {
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role,
        ...(identifier.trim() ? { identifier: identifier.trim() } : {}),
        ...(programId ? { acad_program_id: programId } : {}),
        ...(departmentId ? { department_id: departmentId } : {}),
      }
      const user = await usersApi.create(payload)
      addToast(`${payload.full_name} added successfully.`, 'success')
      onCreated(user)
      reset()
      onClose()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { reset(); onClose() } }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add user</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-3 mt-2">
          <div className="space-y-1">
            <label htmlFor="cu-full-name" className="text-sm font-medium text-gray-700">Full name</label>
            <Input id="cu-full-name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <label htmlFor="cu-email" className="text-sm font-medium text-gray-700">Email</label>
            <Input id="cu-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <label htmlFor="cu-password" className="text-sm font-medium text-gray-700">Temporary password</label>
            <Input id="cu-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Role</label>
            <Select value={role} onValueChange={(v) => { setRole(v as Role); if (v !== 'STUDENT') setProgramId(''); if (v !== 'FACULTY' && v !== 'DEAN') setDepartmentId('') }}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {PRIMARY_ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
            <p className="text-xs text-gray-500">
              GUIDE / EVALUATOR / BOARD are responsibilities — assign them from the faculty member's profile.
            </p>
          </div>
          {role === 'STUDENT' && (
            <ProgramSelect
              value={programId}
              onChange={setProgramId}
              programs={programs}
              required
            />
          )}
          {(role === 'FACULTY' || role === 'DEAN') && (
            <DepartmentSelect
              value={departmentId}
              onChange={setDepartmentId}
              departments={departments}
              required
            />
          )}
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">
              Identifier <span className="text-gray-400 font-normal">(optional — student ID, staff no.)</span>
            </label>
            <Input value={identifier} onChange={(e) => setIdentifier(e.target.value)} placeholder="e.g. ST2024001" />
          </div>
          {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => { reset(); onClose() }}>Cancel</Button>
            <Button type="submit" disabled={loading}>{loading ? 'Creating…' : 'Create user'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Edit dialog
// ---------------------------------------------------------------------------

interface EditDialogProps {
  user: UserRecord | null
  onClose: () => void
  onUpdated: (user: UserRecord) => void
  programs: AcadProgram[]
  departments: Department[]
}

function EditUserDialog({ user, onClose, onUpdated, programs, departments }: EditDialogProps) {
  const [fullName,     setFullName]     = useState('')
  const [email,        setEmail]        = useState('')
  const [role,         setRole]         = useState<Role>('FACULTY')
  const [isActive,     setIsActive]     = useState(true)
  const [identifier,   setIdentifier]   = useState('')
  const [programId,    setProgramId]    = useState('')
  const [departmentId, setDepartmentId] = useState('')
  const [error,        setError]        = useState('')
  const [loading,      setLoading]      = useState(false)

  useEffect(() => {
    if (user) {
      setFullName(user.full_name)
      setEmail(user.email)
      setRole(displayRole(user) as Role)
      setIsActive(user.is_active)
      setIdentifier(user.identifier ?? '')
      setProgramId(user.acad_program_id ?? '')
      setDepartmentId('')
      setError('')
    }
  }, [user])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!user) return
    if (role === 'STUDENT' && !programId) {
      setError('Program is required for students.')
      return
    }
    setError('')
    setLoading(true)
    try {
      const payload: UpdateUserPayload = {}
      if (fullName.trim() !== user.full_name) payload.full_name = fullName.trim()
      if (email.trim().toLowerCase() !== user.email.toLowerCase()) payload.email = email.trim()
      if (role !== user.role) payload.role = role
      if (isActive !== user.is_active) payload.is_active = isActive
      if (identifier.trim() !== (user.identifier ?? '')) payload.identifier = identifier.trim() || undefined
      if (programId !== (user.acad_program_id ?? '')) payload.acad_program_id = programId || undefined
      if (departmentId) payload.department_id = departmentId
      const updated = await usersApi.update(user.id, payload)
      addToast('User updated successfully.', 'success')
      onUpdated(updated)
      onClose()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={!!user} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit user</DialogTitle>
        </DialogHeader>
        {user && (
          <form onSubmit={handleSubmit} className="space-y-3 mt-2">
            <div className="space-y-1">
              <label htmlFor="edit-email" className="text-sm font-medium text-gray-700">Email address</label>
              <Input
                id="edit-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              {email.trim().toLowerCase() !== user.email.toLowerCase() && (
                <p className="text-xs text-amber-600">
                  Changing this email updates the user's sign-in address. Their role, permissions, and existing records remain unchanged.
                </p>
              )}
            </div>
            {user.role === 'GUIDE' && (
              <div className="rounded-lg bg-teal-50 border border-teal-200 px-3 py-2">
                <p className="text-xs font-semibold text-teal-700 mb-1">User UUID <span className="font-normal text-teal-600">(used as guide_user_id in research proposals)</span></p>
                <CopyUuidButton uuid={user.id} />
              </div>
            )}
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Full name</label>
              <Input value={fullName} onChange={(e) => setFullName(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">Role</label>
              <Select value={role} onValueChange={(v) => { setRole(v as Role); if (v !== 'STUDENT') setProgramId('') }}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {/* Primary roles + this user's current role, so legacy standalone
                      GUIDE/EVALUATOR/BOARD accounts still display and can be migrated. */}
                  {Array.from(new Set<string>([...PRIMARY_ROLES, user.role])).map((r) => (
                    <SelectItem key={r} value={r}>{r}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {!(PRIMARY_ROLES as readonly string[]).includes(user.role) && (
                <p className="text-xs text-amber-600">
                  This is a legacy standalone "{user.role}" account. Consider switching it to FACULTY and granting {user.role} as a responsibility from the faculty profile.
                </p>
              )}
            </div>
            {role === 'STUDENT' && (
              <ProgramSelect
                value={programId}
                onChange={setProgramId}
                programs={programs}
                required
              />
            )}
            {(role === 'FACULTY' || role === 'DEAN') && (
              <DepartmentSelect
                value={departmentId}
                onChange={setDepartmentId}
                departments={departments}
              />
            )}
            <div className="space-y-1">
              <label className="text-sm font-medium text-gray-700">
                Identifier <span className="text-gray-400 font-normal">(optional — staff ID, employee no.)</span>
              </label>
              <Input
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                placeholder="e.g. GUIDE001"
              />
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is-active"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-indigo-600"
              />
              <label htmlFor="is-active" className="text-sm font-medium text-gray-700">
                Account active
              </label>
            </div>
            {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={loading}>{loading ? 'Saving…' : 'Save changes'}</Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function UsersPage() {
  const [searchParams] = useSearchParams()
  const [users,        setUsers]        = useState<UserRecord[]>([])
  const [programs,     setPrograms]     = useState<AcadProgram[]>([])
  const [departments,  setDepartments]  = useState<Department[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState('')
  const [showCreate,   setShowCreate]   = useState(false)
  const [editingUser,  setEditingUser]  = useState<UserRecord | null>(null)
  const [filterRole,   setFilterRole]   = useState<string>('ALL')
  const [filterProgram,setFilterProgram]= useState<string>(searchParams.get('program_id') ?? 'ALL')
  const [search,       setSearch]       = useState('')

  useEffect(() => {
    localStorage.setItem('vidya_onboarding_users', '1')
    Promise.all([
      usersApi.list(),
      academicsApi.listPrograms(),
      academicsApi.listDepartments(),
    ])
      .then(([u, p, d]) => { setUsers(u); setPrograms(p); setDepartments(d) })
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  const filtered = users.filter((u) => {
    const matchRole = filterRole === 'ALL' || displayRole(u) === filterRole
    const matchProgram =
      filterProgram === 'ALL' ||
      (u.program_ids ?? []).includes(filterProgram) ||
      u.acad_program_id === filterProgram
    const q = search.toLowerCase()
    const matchSearch = !q ||
      u.full_name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.academic_id ?? '').toLowerCase().includes(q) ||
      (u.department_name ?? '').toLowerCase().includes(q) ||
      (u.program_names ?? []).join(' ').toLowerCase().includes(q)
    return matchRole && matchProgram && matchSearch
  })

  function handleCreated(user: UserRecord) {
    setUsers((prev) => [user, ...prev])
  }

  function handleUpdated(updated: UserRecord) {
    setUsers((prev) => prev.map((u) => u.id === updated.id ? updated : u))
  }

  if (loading) return (
    <PageShell>
      <PageLoading message="Loading users…" />
    </PageShell>
  )

  return (
    <PageShell>
      <PageHeader
        icon={Users}
        title="Academic Ownership"
        subtitle={`${users.length} user${users.length !== 1 ? 's' : ''} · department, program, and ID at a glance`}
        action={<Button onClick={() => setShowCreate(true)}>Add user</Button>}
      />

      {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <Input
          className="w-48"
          placeholder="Search name, dept, program…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select value={filterRole} onValueChange={setFilterRole}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All roles</SelectItem>
            {FILTER_ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={filterProgram} onValueChange={setFilterProgram}>
          <SelectTrigger className="w-44"><SelectValue placeholder="All programs" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All programs</SelectItem>
            {programs.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Academic Ownership Table */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Role</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Department</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Programs</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Academic ID</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-2">
                  {users.length === 0 ? (
                    <PageEmpty
                      icon={Users}
                      title="No users added yet"
                      message="Add faculty, students, and staff to your institution."
                      description="You can add users individually or import them in bulk via CSV."
                      action={
                        <Button size="sm" onClick={() => setShowCreate(true)}>
                          <UserPlus className="h-3.5 w-3.5 mr-1.5" />Add User
                        </Button>
                      }
                    />
                  ) : (
                    <PageEmpty message="No users match your filter." />
                  )}
                </td>
              </tr>
            ) : (
              filtered.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  {/* Name + email stacked */}
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{u.full_name}</div>
                    <div className="text-xs text-gray-400 mt-0.5">{u.email}</div>
                    {u.role === 'GUIDE' && (
                      <div className="mt-0.5">
                        <span className="text-xs text-teal-600 font-medium">UUID: </span>
                        <CopyUuidButton uuid={u.id} />
                      </div>
                    )}
                  </td>
                  {/* Role badge */}
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS[displayRole(u)] ?? 'bg-gray-100 text-gray-700'}`}>
                      {displayRole(u)}
                    </span>
                  </td>
                  {/* Department */}
                  <td className="px-4 py-3 text-gray-600 text-xs">
                    {u.department_name
                      ? <span>{u.department_name}{u.department_code ? <span className="text-gray-400 ml-1">({u.department_code})</span> : null}</span>
                      : <span className="text-gray-300">—</span>}
                  </td>
                  {/* Programs — comma-separated list */}
                  <td className="px-4 py-3 text-gray-600 text-xs max-w-[200px]">
                    {(u.program_names ?? []).length > 0
                      ? <span className="leading-relaxed">{u.program_names.join(', ')}</span>
                      : <span className="text-gray-400 italic">
                          {u.role === 'FACULTY' ? 'No assigned programs'
                           : u.role === 'DEAN'    ? 'No governed programs'
                           : '—'}
                        </span>}
                  </td>
                  {/* Academic ID: faculty_code | USN | blank */}
                  <td className="px-4 py-3 text-xs font-mono text-gray-600">
                    {u.academic_id ?? <span className="text-gray-300">—</span>}
                  </td>
                  {/* Status */}
                  <td className="px-4 py-3">
                    {u.is_active
                      ? <span className="text-green-700 font-medium">Active</span>
                      : <span className="text-gray-400">Inactive</span>}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="outline" onClick={() => setEditingUser(u)}>
                      Edit
                    </Button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <CreateUserDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={handleCreated}
        programs={programs}
        departments={departments}
      />
      <EditUserDialog
        key={editingUser?.id}
        user={editingUser}
        onClose={() => setEditingUser(null)}
        onUpdated={handleUpdated}
        programs={programs}
        departments={departments}
      />
    </PageShell>
  )
}
