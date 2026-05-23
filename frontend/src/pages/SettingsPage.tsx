import { useState, useEffect } from 'react'
import { useAuth } from '@/lib/auth'
import api, { getErrorMessage } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

function prettifySlug(slug: string): string {
  if (!slug) return 'Unknown institution'
  return slug.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

export default function SettingsPage() {
  const { user, refreshUser } = useAuth()

  useEffect(() => {
    localStorage.setItem('vidya_onboarding_settings', '1')
  }, [])

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
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">Manage your account and institution</p>
      </div>

      {/* Institution profile */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
        <h2 className="text-base font-semibold text-gray-800">Institution</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500">Name</p>
            <p className="font-medium text-gray-900 mt-0.5">{prettifySlug(user?.tenantSlug ?? '')}</p>
          </div>
          <div>
            <p className="text-gray-500">Slug</p>
            <p className="font-medium text-gray-900 mt-0.5">{user?.tenantSlug ?? '—'}</p>
          </div>
          <div>
            <p className="text-gray-500">Schema</p>
            <p className="font-mono text-xs text-gray-600 mt-0.5">{user?.schemaName ?? '—'}</p>
          </div>
        </div>
      </section>

      {/* Account profile */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
        <h2 className="text-base font-semibold text-gray-800">Your account</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-gray-500">Name</p>
            <p className="font-medium text-gray-900 mt-0.5">{user?.fullName ?? '—'}</p>
          </div>
          <div>
            <p className="text-gray-500">Email</p>
            <p className="font-medium text-gray-900 mt-0.5">{user?.email ?? '—'}</p>
          </div>
          <div>
            <p className="text-gray-500">Role</p>
            <p className="font-medium text-gray-900 mt-0.5">{user?.role ?? '—'}</p>
          </div>
        </div>
      </section>

      {/* Change password */}
      <section className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
        <h2 className="text-base font-semibold text-gray-800">Change password</h2>
        <form onSubmit={handleChangePassword} className="space-y-3 max-w-sm">
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Current password</label>
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">New password</label>
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium text-gray-700">Confirm new password</label>
            <Input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />
          </div>
          {pwError   && <p className="text-sm text-red-600 bg-red-50 rounded px-3 py-2">{pwError}</p>}
          {pwSuccess && <p className="text-sm text-green-700 bg-green-50 rounded px-3 py-2">Password changed successfully.</p>}
          <Button type="submit" disabled={pwLoading}>
            {pwLoading ? 'Saving…' : 'Change password'}
          </Button>
        </form>
      </section>
    </div>
  )
}
