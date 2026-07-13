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
import { tint } from '@/lib/platformPalette'

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
        background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
        border: '1px solid var(--pc-t-overlay-08)',
      }}
    >
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: tint(iconColor, 9.41), border: `1px solid ${tint(iconColor, 18.82)}` }}
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
const inputStyle = { background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }
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
            background: photo ? undefined : 'linear-gradient(135deg, var(--pc-accent), var(--pc-accent-hover))',
            color: 'var(--pc-accent-fg)',
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
          style={{ background: 'var(--pc-elevated)', border: '1px solid var(--pc-t-overlay-15)' }}
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
            style={{ background: 'var(--pc-elevated)', border: '1px solid var(--pc-t-overlay-15)' }}
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
            style={{ background: 'var(--pc-t-emerald-12)', color: 'var(--pc-emerald-400)', border: '1px solid var(--pc-t-emerald-30)' }}
          >
            Super Admin
          </span>
          {profile.is_active && (
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
              style={{ background: 'var(--pc-t-bluelt-12)', color: 'var(--pc-blue-400)', border: '1px solid var(--pc-t-bluelt-30)' }}
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
        style={{ background: 'var(--pc-t-amber-06)', border: '1px solid var(--pc-t-amber-15)' }}
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
  if (!pwd) return { label: '', color: 'var(--pc-slate-700)', pct: 0 }
  let score = 0
  if (pwd.length >= 8) score++
  if (pwd.length >= 12) score++
  if (/[A-Z]/.test(pwd)) score++
  if (/[0-9]/.test(pwd)) score++
  if (/[^A-Za-z0-9]/.test(pwd)) score++
  if (score <= 1) return { label: 'Weak', color: 'var(--pc-red-500)', pct: 20 }
  if (score === 2) return { label: 'Fair', color: 'var(--pc-amber-500)', pct: 40 }
  if (score === 3) return { label: 'Good', color: 'var(--pc-blue-400)', pct: 65 }
  if (score === 4) return { label: 'Strong', color: 'var(--pc-emerald-500)', pct: 85 }
  return { label: 'Very Strong', color: 'var(--pc-emerald-400)', pct: 100 }
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
        style={{ background: 'var(--pc-t-emerald-08)', border: '1px solid var(--pc-t-emerald-20)' }}
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
          <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--pc-t-overlay-06)' }}>
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
      <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid var(--pc-t-overlay-05)' }}>
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Active Sessions</span>
        <span className="text-sm font-bold text-slate-200">
          {isLoading ? '…' : data?.active_session_count ?? 0}
        </span>
      </div>
      <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid var(--pc-t-overlay-05)' }}>
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
          style={{ background: 'var(--pc-t-emerald-12)', color: 'var(--pc-emerald-400)', border: '1px solid var(--pc-t-emerald-30)' }}
        >
          Super Admin
        </span>
      </div>
      <div
        className="mt-3 rounded-lg px-3 py-2 text-[11px] text-slate-600"
        style={{ background: 'var(--pc-t-overlay-2p5)', border: '1px solid var(--pc-t-overlay-05)' }}
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
          style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
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
          <SectionCard icon={User} title="Account Info" iconColor="var(--pc-indigo-500)">
            <ProfileView profile={profile} />
            <div style={{ borderTop: '1px solid var(--pc-t-overlay-06)', marginTop: 20, paddingTop: 16 }}>
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
          <SectionCard icon={Shield} title="Security" iconColor="var(--pc-emerald-500)">
            <SecurityInfo />
          </SectionCard>

          {/* Change Email */}
          <SectionCard icon={Mail} title="Change Email" iconColor="var(--pc-blue-400)">
            <ChangeEmailForm />
          </SectionCard>

          {/* Change Password */}
          <SectionCard icon={Lock} title="Change Password" iconColor="var(--pc-amber-500)">
            <ChangePasswordForm />
          </SectionCard>

        </div>
      )}
    </main>
  )
}
