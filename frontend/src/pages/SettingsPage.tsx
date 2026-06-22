import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import api, { getErrorMessage } from '@/lib/api'
import { usersApi } from '@/lib/api/users'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Building2, ShieldCheck, Palette, Mail, Database, Lock, Pencil, X, Check } from 'lucide-react'

function prettifySlug(slug: string): string {
  if (!slug) return 'Unknown institution'
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

export default function SettingsPage() {
  const { user, refreshUser } = useAuth()

  useEffect(() => {
    localStorage.setItem('vidya_onboarding_settings', '1')
  }, [])

  const [editingName,  setEditingName]  = useState(false)
  const [nameValue,    setNameValue]    = useState(user?.fullName ?? '')
  const [nameSaving,   setNameSaving]   = useState(false)
  const [nameError,    setNameError]    = useState('')

  useEffect(() => {
    setNameValue(user?.fullName ?? '')
  }, [user?.fullName])

  async function handleSaveName() {
    const trimmed = nameValue.trim()
    if (!trimmed || trimmed === user?.fullName) { setEditingName(false); return }
    setNameSaving(true)
    setNameError('')
    try {
      await usersApi.update(user!.id, { full_name: trimmed })
      await refreshUser()
      setEditingName(false)
    } catch (err) {
      setNameError(getErrorMessage(err))
    } finally {
      setNameSaving(false)
    }
  }

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword,     setNewPassword]     = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [pwError,         setPwError]         = useState('')
  const [pwSuccess,       setPwSuccess]       = useState(false)
  const [pwLoading,       setPwLoading]       = useState(false)

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault()
    setPwError('')
    setPwSuccess(false)

    if (newPassword !== confirmPassword) {
      setPwError('New passwords do not match.')
      return
    }
    if (newPassword.length < 8) {
      setPwError('New password must be at least 8 characters.')
      return
    }
    if (newPassword === currentPassword) {
      setPwError('New password must be different from your current password.')
      return
    }

    setPwLoading(true)
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      await refreshUser()
      setPwSuccess(true)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err) {
      setPwError(getErrorMessage(err))
    } finally {
      setPwLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f4f7ff] px-4 py-8">
      <div className="mx-auto flex max-w-5xl flex-col gap-6">
        {/* Page header */}
        <header className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <p className="text-xs font-semibold tracking-[0.2em] text-sv-primary uppercase">Settings</p>
            <h1 className="mt-1 text-2xl font-black tracking-tight text-slate-900">
              Tenant workspace &nbsp;
              <span className="text-sv-primary">preferences</span>
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Manage your institution profile, account, branding, and security for VIDYA AI.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 shadow-sm">
            <img
              src="/branding/sherpavector-logo.png"
              alt="VIDYA AI"
              className="h-9 w-9 rounded-lg object-contain"
            />
            <div className="text-right">
              <p className="text-xs font-semibold text-slate-700">VIDYA AI</p>
              <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-400">
                Academic AI Workspace
              </p>
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1.6fr)]">
          {/* Left column: institution + admin + branding */}
          <div className="space-y-6">
            {/* Institution profile */}
            <section className="rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-[0_14px_40px_rgba(15,23,42,0.06)] sm:p-6">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sv-primary/10 text-sv-primary">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">Institution profile</h2>
                    <p className="text-xs text-slate-500">Schema-per-institution tenancy</p>
                  </div>
                </div>
                <span className="rounded-full bg-sv-light px-3 py-1 text-[11px] font-semibold text-sv-primary">
                  Tenant: {user?.tenantSlug ?? '—'}
                </span>
              </div>

              <div className="grid gap-4 text-sm sm:grid-cols-2">
                <div>
                  <p className="text-slate-500">Institution name</p>
                  <p className="mt-0.5 font-medium text-slate-900">
                    {prettifySlug(user?.tenantSlug ?? '')}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Slug</p>
                  <p className="mt-0.5 font-mono text-xs text-slate-800">
                    {user?.tenantSlug ?? '—'}
                  </p>
                </div>
                <div>
                  <p className="text-slate-500">Database schema</p>
                  <div className="mt-0.5 inline-flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5">
                    <Database className="h-3.5 w-3.5 text-slate-400" />
                    <span className="font-mono text-[11px] text-slate-700">
                      {user?.schemaName ?? '—'}
                    </span>
                  </div>
                </div>
                <div>
                  <p className="text-slate-500">Workspace status</p>
                  <span className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    Active
                  </span>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-slate-50 px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900/90">
                    <img
                      src="/branding/sherpavector-logo.png"
                      alt="Institution logo"
                      className="h-7 w-7 object-contain"
                    />
                  </div>
                  <div className="text-xs">
                    <p className="font-semibold text-slate-800">Institution branding</p>
                    <p className="text-slate-500">
                      Managed centrally via VIDYA AI platform console.
                    </p>
                  </div>
                </div>
              </div>
            </section>

            {/* Admin profile */}
            <section className="rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-[0_14px_40px_rgba(15,23,42,0.06)] sm:p-6">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="relative flex h-11 w-11 items-center justify-center rounded-full bg-sv-primary/10 text-sv-primary">
                    <span className="text-sm font-semibold">
                      {(user?.fullName ?? user?.email ?? 'A')
                        .split(' ')
                        .map((p) => p[0])
                        .join('')
                        .slice(0, 2)
                        .toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">Admin profile</h2>
                    <p className="text-xs text-slate-500">Used for all VIDYA AI workspace actions.</p>
                  </div>
                </div>
                <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold text-emerald-700">
                  <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Account active
                </span>
              </div>

              <div className="grid gap-4 text-sm sm:grid-cols-2">
                <div className="sm:col-span-2">
                  <p className="text-slate-500 mb-1">Name</p>
                  {editingName ? (
                    <div className="flex items-center gap-2">
                      <Input
                        value={nameValue}
                        onChange={e => setNameValue(e.target.value)}
                        className="h-9 text-sm rounded-lg border-slate-200 max-w-xs"
                        autoFocus
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleSaveName()
                          if (e.key === 'Escape') { setEditingName(false); setNameValue(user?.fullName ?? '') }
                        }}
                      />
                      <button
                        onClick={handleSaveName}
                        disabled={nameSaving}
                        className="p-1.5 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                        title="Save"
                      >
                        <Check className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => { setEditingName(false); setNameValue(user?.fullName ?? '') }}
                        className="p-1.5 rounded-lg bg-slate-100 text-slate-500 hover:bg-slate-200"
                        title="Cancel"
                      >
                        <X className="h-4 w-4" />
                      </button>
                      {nameError && <p className="text-xs text-red-500">{nameError}</p>}
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-slate-900">{user?.fullName ?? '—'}</p>
                      <button
                        onClick={() => setEditingName(true)}
                        className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                        title="Edit name"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}
                </div>
                <div>
                  <p className="text-slate-500">Role</p>
                  <p className="mt-0.5 font-medium text-slate-900">{user?.role ?? '—'}</p>
                </div>
                <div>
                  <p className="text-slate-500">Email</p>
                  <div className="mt-0.5 inline-flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-1.5">
                    <Mail className="h-3.5 w-3.5 text-slate-400" />
                    <span className="text-sm font-medium text-slate-900">{user?.email ?? '—'}</span>
                  </div>
                </div>
              </div>
            </section>

            {/* Branding & appearance */}
            <section className="rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-[0_14px_40px_rgba(15,23,42,0.06)] sm:p-6">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sv-primary/10 text-sv-primary">
                    <Palette className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-sm font-semibold text-slate-900">Branding & appearance</h2>
                    <p className="text-xs text-slate-500">
                      Customize your institution's Academic AI Workspace theme.
                    </p>
                  </div>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
                <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                    Product identity
                  </p>
                  <div className="mt-3 flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900">
                      <img
                        src="/branding/sherpavector-logo.png"
                        alt="VIDYA AI"
                        className="h-7 w-7 object-contain"
                      />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">VIDYA AI</p>
                      <p className="text-[11px] text-slate-500">Enterprise Academic Intelligence Platform</p>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center gap-2 text-[11px] text-slate-500">
                    <span className="inline-flex h-4 w-4 rounded-full bg-sv-primary/10 ring-2 ring-sv-primary/40" />
                    <span className="inline-flex h-4 w-4 rounded-full bg-sv-accent/10 ring-2 ring-sv-accent/40" />
                    <span className="inline-flex h-4 w-4 rounded-full bg-slate-900/90 ring-2 ring-slate-900/40" />
                    <span className="ml-1">Platform palette preview</span>
                  </div>
                </div>

                <div className="flex flex-col justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50/60 p-4 text-xs">
                  <div>
                    <p className="font-semibold text-slate-800">Institution logo & theme</p>
                    <p className="mt-1 text-slate-500">
                      Upload your institution logo and set your brand colors. Changes apply to the
                      login page and workspace sidebar.
                    </p>
                  </div>
                  <a
                    href="/settings/branding"
                    className="inline-flex w-fit items-center gap-2 rounded-full bg-sv-primary text-[11px] font-semibold text-white px-3 py-1.5 hover:bg-blue-700 transition-colors"
                  >
                    <Palette className="h-3.5 w-3.5" />
                    Manage Branding
                  </a>
                </div>
              </div>
            </section>
          </div>

          {/* Right column: security & password */}
          <div className="space-y-6">
            {/* Security overview */}
            <section className="rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-[0_14px_40px_rgba(15,23,42,0.06)] sm:p-6">
              <div className="mb-3 flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">Security posture</h2>
                  <p className="text-xs text-slate-500">
                    Passwords are hashed and never stored in plaintext. Sessions are scoped per
                    institution.
                  </p>
                </div>
              </div>
              <ul className="mt-3 space-y-1.5 text-xs text-slate-500">
                <li className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Role-based access for VIDYA AI tenant administrators.
                </li>
                <li className="flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Automatic session revocation on password change.
                </li>
              </ul>
            </section>

            {/* Change password */}
            <section className="rounded-2xl border border-slate-200 bg-white/95 p-5 shadow-[0_18px_50px_rgba(15,23,42,0.08)] sm:p-6">
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sv-primary/10 text-sv-primary">
                  <Lock className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold text-slate-900">Change password</h2>
                  <p className="text-xs text-slate-500">
                    Update your credentials for this tenant. This does not affect other institutions.
                  </p>
                </div>
              </div>

              <form onSubmit={handleChangePassword} className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    Current password
                  </label>
                  <Input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                    className="h-10 rounded-lg border-slate-200 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    New password
                  </label>
                  <Input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    className="h-10 rounded-lg border-slate-200 text-sm"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
                    Confirm new password
                  </label>
                  <Input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    className="h-10 rounded-lg border-slate-200 text-sm"
                  />
                </div>
                {pwError && (
                  <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 border border-red-100">
                    {pwError}
                  </p>
                )}
                {pwSuccess && (
                  <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700 border border-emerald-100">
                    Password changed successfully.
                  </p>
                )}
                <div className="flex items-center justify-between gap-3 pt-1">
                  <Button
                    type="submit"
                    disabled={pwLoading}
                    className="h-10 rounded-xl bg-sv-primary px-5 text-sm font-semibold text-white shadow-[0_12px_28px_rgba(37,99,235,0.25)] hover:bg-blue-700"
                  >
                    {pwLoading ? 'Saving…' : 'Change password'}
                  </Button>
                  <p className="max-w-[180px] text-[11px] text-slate-500">
                    Changing your password will sign out active sessions across devices for this
                    tenant.
                  </p>
                </div>
              </form>
            </section>
          </div>
        </div>
      </div>
    </div>
  )
}
