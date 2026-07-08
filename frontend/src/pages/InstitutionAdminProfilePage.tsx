import { useState } from 'react'
import { Link } from 'react-router-dom'
import { UserCircle2, Pencil, Check, X, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/lib/auth'
import { AvatarUpload } from '@/components/shared/AvatarUpload'
import { getErrorMessage } from '@/lib/api'
import { usersApi } from '@/lib/api/users'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { addToast } from '@/hooks/useToast'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
      {children}
    </div>
  )
}

function getInitials(name: string) {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function InstitutionAdminProfilePage() {
  const { user, refreshUser } = useAuth()

  // Name edit
  const [editingName, setEditingName] = useState(false)
  const [nameValue,   setNameValue]   = useState(user?.fullName ?? '')
  const [nameLoading, setNameLoading] = useState(false)

  // Email edit
  const [editingEmail, setEditingEmail] = useState(false)
  const [emailValue,   setEmailValue]   = useState(user?.email ?? '')
  const [emailLoading, setEmailLoading] = useState(false)

  async function saveName() {
    if (!user?.id || !nameValue.trim()) return
    setNameLoading(true)
    try {
      await usersApi.update(user.id, { full_name: nameValue.trim() })
      await refreshUser()
      setEditingName(false)
      addToast('Display name updated.', 'success')
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    } finally {
      setNameLoading(false)
    }
  }

  async function saveEmail() {
    if (!user?.id || !emailValue.trim()) return
    setEmailLoading(true)
    try {
      await usersApi.update(user.id, { email: emailValue.trim() })
      await refreshUser()
      setEditingEmail(false)
      addToast('Email updated. You may need to log in again.', 'success')
    } catch (err) {
      addToast(getErrorMessage(err), 'error')
    } finally {
      setEmailLoading(false)
    }
  }

  const initials = user?.fullName ? getInitials(user.fullName) : 'AD'

  return (
    <PageShell>
      <PageHeader
        icon={UserCircle2}
        title="My Profile"
        subtitle="Manage your account information and security settings"
      />

      <div className="max-w-2xl space-y-6">

        {/* Identity card */}
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          {/* Avatar strip */}
          <div className="px-6 py-5 flex items-center gap-4 border-b border-gray-100">
            <AvatarUpload
              initials={initials}
              shape="square"
              style={{ background: 'rgba(99,102,241,0.08)', color: '#4f46e5', border: '1px solid rgba(99,102,241,0.30)' }}
            />
            <div>
              <p className="text-base font-bold text-gray-900">{user?.fullName}</p>
              <p className="text-xs text-gray-500">{user?.email}</p>
              <p className="text-xs text-indigo-600 font-semibold mt-0.5 uppercase tracking-wide">
                {user?.role}
              </p>
            </div>
          </div>

          {/* Fields */}
          <div className="px-6 py-5 space-y-5">
            {/* Display name */}
            <Field label="Display name">
              {editingName ? (
                <div className="flex items-center gap-2">
                  <Input
                    value={nameValue}
                    onChange={e => setNameValue(e.target.value)}
                    className="flex-1"
                    autoFocus
                  />
                  <Button size="sm" onClick={saveName} disabled={nameLoading || !nameValue.trim()}>
                    <Check className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { setEditingName(false); setNameValue(user?.fullName ?? '') }}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-900">{user?.fullName}</span>
                  <Button size="sm" variant="ghost" onClick={() => { setEditingName(true); setNameValue(user?.fullName ?? '') }}
                    className="text-xs gap-1">
                    <Pencil className="h-3 w-3" /> Edit
                  </Button>
                </div>
              )}
            </Field>

            {/* Email */}
            <Field label="Email address">
              {editingEmail ? (
                <div className="flex items-center gap-2">
                  <Input
                    type="email"
                    value={emailValue}
                    onChange={e => setEmailValue(e.target.value)}
                    className="flex-1"
                    autoFocus
                  />
                  <Button size="sm" onClick={saveEmail} disabled={emailLoading || !emailValue.trim()}>
                    <Check className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => { setEditingEmail(false); setEmailValue(user?.email ?? '') }}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-900">{user?.email}</span>
                  <Button size="sm" variant="ghost" onClick={() => { setEditingEmail(true); setEmailValue(user?.email ?? '') }}
                    className="text-xs gap-1">
                    <Pencil className="h-3 w-3" /> Edit
                  </Button>
                </div>
              )}
            </Field>

            {/* Role */}
            <Field label="Role">
              <span className="inline-flex items-center px-2.5 py-0.5 rounded text-xs font-semibold bg-indigo-100 text-indigo-800">
                {user?.role}
              </span>
            </Field>
          </div>
        </section>

        {/* Security — link to Settings */}
        <section className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-800">Security</h2>
          </div>
          <div className="px-6 py-5 flex items-center justify-between">
            <p className="text-sm text-gray-600">Password and security settings are managed in Settings.</p>
            <Button asChild size="sm" variant="outline">
              <Link to="/settings">Go to Settings</Link>
            </Button>
          </div>
        </section>

      </div>
    </PageShell>
  )
}
