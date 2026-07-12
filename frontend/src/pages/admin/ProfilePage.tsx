import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  User, Mail, Lock, Shield, RefreshCw, Camera, Eye, EyeOff, CheckCircle2, Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { addToast } from '@/hooks/useToast'
import { getAdminErrorMessage } from '@/lib/adminApi'
import {
  AVATAR_ACCEPT,
  AvatarUploadError,
  isDisplayableImageUrl,
  removePlatformAvatar,
  uploadPlatformAvatar,
} from '@/lib/api/avatar'
import {
  getPlatformProfile,
  getPlatformSessions,
  updatePlatformProfile,
  updatePlatformEmail,
  changePlatformPassword,
} from '@/lib/api/platform'

// ---------------------------------------------------------------------------
// Shared UI primitives
// ---------------------------------------------------------------------------

function SectionCard({
  icon: Icon, title, iconColor, children,
}: {
  icon: typeof User; title: string; iconColor: string; children: React.ReactNode
}) {
  return (
    <div
      className="rounded-xl p-6"
      style={{
        background: 'linear-gradient(180deg, rgba(14,24,45,0.95) 0%, rgba(10,18,35,0.95) 100%)',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: iconColor + '18', border: `1px solid ${iconColor}30` }}
        >
          <Icon className="h-[18px] w-[18px]" style={{ color: iconColor }} />
        </div>
        <h2 className="text-base font-bold text-white">{title}</h2>
      </div>
      {children}
    </div>
  )
}

const inputCls = 'w-full px-3 py-2.5 text-sm text-slate-200 rounded-lg outline-none transition-all'
const inputStyle = { background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }
const labelCls = 'block text-xs font-semibold text-slate-400 mb-1.5'

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className={labelCls}>{label}</label>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// View Profile section
// ---------------------------------------------------------------------------

function ProfileView({ profile }: { profile: ReturnType<typeof getPlatformProfile> extends Promise<infer T> ? T : never }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)

  const initials = profile.full_name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)

  const photo = isDisplayableImageUrl(profile.avatar_url) ? profile.avatar_url : null

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBusy(true)
    try {
      await uploadPlatformAvatar(file)
      await qc.invalidateQueries({ queryKey: ['platform-profile'] })
      addToast('Profile picture updated.', 'success')
    } catch (err) {
      addToast(err instanceof AvatarUploadError ? err.message : getAdminErrorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  async function onRemove() {
    setBusy(true)
    try {
      await removePlatformAvatar()
      await qc.invalidateQueries({ queryKey: ['platform-profile'] })
      addToast('Profile picture removed.', 'success')
    } catch (err) {
      addToast(getAdminErrorMessage(err), 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-start gap-5">
      <div className="relative w-16 h-16 flex-shrink-0">
        <div
          className="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold text-white"
          style={{
            background: photo ? undefined : 'linear-gradient(135deg, #10b981, #059669)',
            backgroundImage: photo ? `url(${photo})` : undefined,
            backgroundSize: 'cover',
            backgroundPosition: 'center',
          }}
        >
          {!photo && initials}
        </div>
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={busy}
          className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full flex items-center justify-center text-slate-300 disabled:opacity-60"
          style={{ background: '#0e182d', border: '1px solid rgba(255,255,255,0.15)' }}
          aria-label="Change profile picture"
          title="Change profile picture (JPG, JPEG, PNG, WEBP)"
        >
          {busy ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Camera className="h-3 w-3" />}
        </button>
        {photo && !busy && (
          <button
            type="button"
            onClick={onRemove}
            className="absolute -bottom-1 -left-1 h-6 w-6 rounded-full flex items-center justify-center text-slate-400 hover:text-red-400"
            style={{ background: '#0e182d', border: '1px solid rgba(255,255,255,0.15)' }}
            aria-label="Remove profile picture"
            title="Remove profile picture"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        )}
        <input ref={fileRef} type="file" accept={AVATAR_ACCEPT} className="hidden" onChange={onPick} />
      </div>
      <div className="flex-1 min-w-0 space-y-2">
        <div>
          <p className="text-lg font-bold text-white">{profile.full_name}</p>
          <p className="text-sm text-slate-400">{profile.email}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
            style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399', border: '1px solid rgba(16,185,129,0.3)' }}
          >
            Super Admin
          </span>
          {profile.is_active && (
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
              style={{ background: 'rgba(96,165,250,0.12)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.3)' }}
            >
              Active
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 pt-1">
          {profile.created_at && (
            <p className="text-xs text-slate-500">
              <span className="text-slate-600">Joined </span>
              {new Date(profile.created_at).toLocaleDateString()}
            </p>
          )}
          {profile.last_login_at && (
            <p className="text-xs text-slate-500">
              <span className="text-slate-600">Last login </span>
              {new Date(profile.last_login_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Edit Profile section
// ---------------------------------------------------------------------------

function EditProfileForm({ profile, onSuccess }: {
  profile: ReturnType<typeof getPlatformProfile> extends Promise<infer T> ? T : never
  onSuccess: () => void
}) {
  const qc = useQueryClient()
  const [name, setName] = useState(profile.full_name)

  const mut = useMutation({
    // The picture is set by uploading it on the profile card above, not by
    // pasting a URL — so this form only carries the display name.
    mutationFn: () => updatePlatformProfile({
      full_name: name !== profile.full_name ? name : undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['platform-profile'] })
      addToast('Profile updated.', 'success')
      onSuccess()
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
  })

  return (
    <div className="space-y-4">
      <Field label="Display name">
        <input
          className={inputCls}
          style={inputStyle}
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
        />
      </Field>
      <Button
        onClick={() => mut.mutate()}
        disabled={mut.isPending || (!name.trim())}
        className="w-full"
      >
        {mut.isPending ? 'Saving…' : 'Save Changes'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Change Email section
// ---------------------------------------------------------------------------

function ChangeEmailForm() {
  const qc = useQueryClient()
  const [newEmail, setNewEmail] = useState('')
  const [currentPwd, setCurrentPwd] = useState('')
  const [showPwd, setShowPwd] = useState(false)

  const mut = useMutation({
    mutationFn: () => updatePlatformEmail({ new_email: newEmail, current_password: currentPwd }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['platform-profile'] })
      addToast('Email updated successfully.', 'success')
      setNewEmail('')
      setCurrentPwd('')
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
  })

  return (
    <div className="space-y-4">
      <Field label="New email address">
        <input
          type="email"
          className={inputCls}
          style={inputStyle}
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="new@example.com"
          autoComplete="off"
        />
      </Field>
      <Field label="Current password (required)">
        <div className="relative">
          <input
            type={showPwd ? 'text' : 'password'}
            className={`${inputCls} pr-10`}
            style={inputStyle}
            value={currentPwd}
            onChange={(e) => setCurrentPwd(e.target.value)}
            placeholder="Enter your current password"
            autoComplete="current-password"
          />
          <button
            type="button"
            onClick={() => setShowPwd(!showPwd)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300"
          >
            {showPwd ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </Field>
      <div
        className="rounded-lg px-3 py-2 text-xs text-slate-500"
        style={{ background: 'rgba(245,158,11,0.06)', border: '1px solid rgba(245,158,11,0.15)' }}
      >
        Changing your email will update your login credentials. You'll need to use the new email for future logins.
      </div>
      <Button
        onClick={() => mut.mutate()}
        disabled={mut.isPending || !newEmail || !currentPwd}
        className="w-full"
      >
        {mut.isPending ? 'Updating…' : 'Update Email'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Change Password section
// ---------------------------------------------------------------------------

function strength(pwd: string): { label: string; color: string; pct: number } {
  if (!pwd) return { label: '', color: '#334155', pct: 0 }
  let score = 0
  if (pwd.length >= 8) score++
  if (pwd.length >= 12) score++
  if (/[A-Z]/.test(pwd)) score++
  if (/[0-9]/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++
  if (score <= 1) return { label: 'Weak', color: '#ef4444', pct: 20 }
  if (score === 2) return { label: 'Fair', color: '#f59e0b', pct: 40 }
  if (score === 3) return { label: 'Good', color: '#60a5fa', pct: 65 }
  if (score === 4) return { label: 'Strong', color: '#10b981', pct: 85 }
  return { label: 'Very Strong', color: '#34d399', pct: 100 }
}

function ChangePasswordForm() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [show, setShow] = useState({ current: false, next: false, confirm: false })
  const [done, setDone] = useState(false)

  const str = strength(next)
  const mismatch = confirm.length > 0 && next !== confirm

  const mut = useMutation({
    mutationFn: () => changePlatformPassword({
      current_password: current,
      new_password: next,
      confirm_password: confirm,
    }),
    onSuccess: () => {
      addToast('Password changed. All other sessions terminated.', 'success')
      setCurrent('')
      setNext('')
      setConfirm('')
      setDone(true)
    },
    onError: (err) => addToast(getAdminErrorMessage(err), 'error'),
  })

  if (done) {
    return (
      <div
        className="rounded-lg px-4 py-5 flex items-center gap-3"
        style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}
      >
        <CheckCircle2 className="h-5 w-5 text-emerald-400 flex-shrink-0" />
        <div>
          <p className="text-sm font-semibold text-emerald-300">Password changed successfully</p>
          <p className="text-xs text-slate-500 mt-0.5">All other active sessions have been terminated.</p>
        </div>
        <button onClick={() => setDone(false)} className="ml-auto text-xs text-slate-500 hover:text-slate-300">
          Change again
        </button>
      </div>
    )
  }

  function toggleShow(field: keyof typeof show) {
    setShow((s) => ({ ...s, [field]: !s[field] }))
  }

  function PasswordField({ label, value, onChange, field, placeholder }: {
    label: string; value: string; onChange: (v: string) => void
    field: keyof typeof show; placeholder?: string
  }) {
    return (
      <Field label={label}>
        <div className="relative">
          <input
            type={show[field] ? 'text' : 'password'}
            className={`${inputCls} pr-10`}
            style={inputStyle}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            autoComplete={field === 'current' ? 'current-password' : 'new-password'}
          />
          <button
            type="button"
            onClick={() => toggleShow(field)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 hover:text-slate-300"
          >
            {show[field] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
      </Field>
    )
  }

  return (
    <div className="space-y-4">
      <PasswordField label="Current password" value={current} onChange={setCurrent} field="current" />
      <PasswordField label="New password" value={next} onChange={setNext} field="next" />

      {next.length > 0 && (
        <div className="space-y-1">
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{ width: `${str.pct}%`, background: str.color }}
            />
          </div>
          {str.label && (
            <p className="text-[11px] font-semibold" style={{ color: str.color }}>{str.label}</p>
          )}
        </div>
      )}

      <PasswordField label="Confirm new password" value={confirm} onChange={setConfirm} field="confirm" />
      {mismatch && (
        <p className="text-[11px] text-red-400">Passwords do not match.</p>
      )}

      <Button
        onClick={() => mut.mutate()}
        disabled={mut.isPending || !current || !next || !confirm || mismatch}
        className="w-full"
      >
        {mut.isPending ? 'Changing…' : 'Change Password'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Security Info section
// ---------------------------------------------------------------------------

function SecurityInfo() {
  const { data, isLoading } = useQuery({
    queryKey: ['platform-sessions'],
    queryFn: getPlatformSessions,
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Active Sessions</span>
        <span className="text-sm font-bold text-slate-200">
          {isLoading ? '…' : data?.active_session_count ?? 0}
        </span>
      </div>
      <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Last Login</span>
        <span className="text-sm text-slate-300">
          {isLoading ? '…' : data?.last_login_at
            ? new Date(data.last_login_at).toLocaleString()
            : '—'}
        </span>
      </div>
      <div className="flex items-center justify-between py-2.5">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Role</span>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
          style={{ background: 'rgba(16,185,129,0.12)', color: '#34d399', border: '1px solid rgba(16,185,129,0.3)' }}
        >
          Super Admin
        </span>
      </div>
      <div
        className="mt-3 rounded-lg px-3 py-2 text-[11px] text-slate-600"
        style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.05)' }}
      >
        Changing your password will immediately terminate all other sessions.
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ProfilePage() {
  const [editingProfile, setEditingProfile] = useState(false)

  const { data: profile, isLoading, isError, refetch } = useQuery({
    queryKey: ['platform-profile'],
    queryFn: getPlatformProfile,
  })

  return (
    <main className="max-w-screen-lg mx-auto px-8 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">My Profile</h1>
        <p className="text-sm text-slate-400 mt-0.5">Manage your Super Admin account and security settings</p>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-24 text-slate-600">
          <RefreshCw className="h-5 w-5 animate-spin mr-2" />
          Loading profile…
        </div>
      )}

      {isError && (
        <div
          className="rounded-xl px-6 py-5 mb-6 flex items-center gap-3"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
        >
          <Shield className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-sm font-semibold text-red-300">Failed to load profile</p>
          <button
            onClick={() => refetch()}
            className="ml-auto text-xs text-slate-400 hover:text-slate-200"
          >
            Retry
          </button>
        </div>
      )}

      {profile && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Profile View + Edit */}
          <SectionCard icon={User} title="Account Info" iconColor="#6366f1">
            <ProfileView profile={profile} />
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', marginTop: 20, paddingTop: 16 }}>
              {editingProfile ? (
                <EditProfileForm
                  profile={profile}
                  onSuccess={() => setEditingProfile(false)}
                />
              ) : (
                <Button
                  variant="ghost"
                  className="w-full text-sm text-slate-400"
                  onClick={() => setEditingProfile(true)}
                >
                  Edit profile
                </Button>
              )}
            </div>
          </SectionCard>

          {/* Security info */}
          <SectionCard icon={Shield} title="Security" iconColor="#10b981">
            <SecurityInfo />
          </SectionCard>

          {/* Change Email */}
          <SectionCard icon={Mail} title="Change Email" iconColor="#60a5fa">
            <ChangeEmailForm />
          </SectionCard>

          {/* Change Password */}
          <SectionCard icon={Lock} title="Change Password" iconColor="#f59e0b">
            <ChangePasswordForm />
          </SectionCard>

        </div>
      )}
    </main>
  )
}
