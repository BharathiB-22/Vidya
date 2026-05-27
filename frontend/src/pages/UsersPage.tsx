import { useEffect, useState, useCallback } from 'react'
import { Users } from 'lucide-react'
import { usersApi, UserRecord, CreateUserPayload, UpdateUserPayload } from '@/lib/api/users'
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

const ROLES = ['ADMIN', 'DEAN', 'FACULTY', 'STUDENT', 'BOARD', 'GUIDE', 'EVALUATOR'] as const
type Role = typeof ROLES[number]

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
// UUID copy button (used in table row and edit dialog for GUIDE users)
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
// Create dialog
// ---------------------------------------------------------------------------

interface CreateDialogProps {
  open: boolean
  onClose: () => void
  onCreated: (user: UserRecord) => void
}

function CreateUserDialog({ open, onClose, onCreated }: CreateDialogProps) {
  const [email,      setEmail]      = useState('')
  const [fullName,   setFullName]   = useState('')
  const [password,   setPassword]   = useState('')
  const [role,       setRole]       = useState<Role>('FACULTY')
  const [identifier, setIdentifier] = useState('')
  const [error,      setError]      = useState('')
  const [loading,    setLoading]    = useState(false)

  function reset() {
    setEmail(''); setFullName(''); setPassword(''); setRole('FACULTY')
    setIdentifier(''); setError('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const payload: CreateUserPayload = {
        email: email.trim(),
        full_name: fullName.trim(),
        password,
        role,
        ...(identifier.trim() ? { identifier: identifier.trim() } : {}),
      }
      const user = await usersApi.create(payload)
      addToast('User created.', 'success')
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
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
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
}

function EditUserDialog({ user, onClose, onUpdated }: EditDialogProps) {
  const [fullName,   setFullName]   = useState('')
  const [role,       setRole]       = useState<Role>('FACULTY')
  const [isActive,   setIsActive]   = useState(true)
  const [identifier, setIdentifier] = useState('')
  const [error,      setError]      = useState('')
  const [loading,    setLoading]    = useState(false)

  useEffect(() => {
    if (user) {
      setFullName(user.full_name)
      setRole(user.role as Role)
      setIsActive(user.is_active)
      setIdentifier(user.identifier ?? '')
      setError('')
    }
  }, [user])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!user) return
    setError('')
    setLoading(true)
    try {
      const payload: UpdateUserPayload = {}
      if (fullName.trim() !== user.full_name) payload.full_name = fullName.trim()
      if (role !== user.role) payload.role = role
      if (isActive !== user.is_active) payload.is_active = isActive
      if (identifier.trim() !== (user.identifier ?? '')) payload.identifier = identifier.trim() || undefined
      const updated = await usersApi.update(user.id, payload)
      addToast('Changes saved.', 'success')
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
            <p className="text-sm text-gray-500">{user.email}</p>
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
              <Select value={role} onValueChange={(v) => setRole(v as Role)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
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
  const [users,        setUsers]        = useState<UserRecord[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState('')
  const [showCreate,   setShowCreate]   = useState(false)
  const [editingUser,  setEditingUser]  = useState<UserRecord | null>(null)
  const [filterRole,   setFilterRole]   = useState<string>('ALL')
  const [search,       setSearch]       = useState('')

  useEffect(() => {
    localStorage.setItem('vidya_onboarding_users', '1')
    usersApi.list()
      .then(setUsers)
      .catch((err) => setError(getErrorMessage(err)))
      .finally(() => setLoading(false))
  }, [])

  const filtered = users.filter((u) => {
    const matchRole = filterRole === 'ALL' || u.role === filterRole
    const q = search.toLowerCase()
    const matchSearch = !q ||
      u.full_name.toLowerCase().includes(q) ||
      u.email.toLowerCase().includes(q) ||
      (u.identifier ?? '').toLowerCase().includes(q)
    return matchRole && matchSearch
  })

  function handleCreated(user: UserRecord) {
    setUsers((prev) => [user, ...prev])
  }

  function handleUpdated(updated: UserRecord) {
    setUsers((prev) => prev.map((u) => u.id === updated.id ? updated : u))
  }

  if (loading) return <PageLoading />

  return (
    <PageShell>
      <PageHeader
        icon={Users}
        title="Users"
        subtitle={`${users.length} user${users.length !== 1 ? 's' : ''} in this institution`}
        action={<Button onClick={() => setShowCreate(true)}>Add user</Button>}
      />

      {error && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{error}</p>}

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <Input
          className="w-48"
          placeholder="Search name, email, ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select value={filterRole} onValueChange={setFilterRole}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All roles</SelectItem>
            {ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Email</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Role</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Identifier</th>
              <th className="text-left px-4 py-2.5 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  {users.length === 0 ? 'No users yet. Add the first one.' : 'No users match your filter.'}
                </td>
              </tr>
            ) : (
              filtered.map((u) => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{u.full_name}</td>
                  <td className="px-4 py-3 text-gray-600">{u.email}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${ROLE_COLORS[u.role] ?? 'bg-gray-100 text-gray-700'}`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {u.identifier ?? '—'}
                    {u.role === 'GUIDE' && (
                      <div className="mt-0.5">
                        <span className="text-xs text-teal-600 font-medium">UUID: </span>
                        <CopyUuidButton uuid={u.id} />
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="text-green-700 font-medium">Active</span>
                    ) : (
                      <span className="text-gray-400">Inactive</span>
                    )}
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

      <CreateUserDialog open={showCreate} onClose={() => setShowCreate(false)} onCreated={handleCreated} />
      <EditUserDialog user={editingUser} onClose={() => setEditingUser(null)} onUpdated={handleUpdated} />
    </PageShell>
  )
}
