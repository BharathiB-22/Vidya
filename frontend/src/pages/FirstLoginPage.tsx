import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import api, { getErrorMessage } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

export default function FirstLoginPage() {
  const navigate = useNavigate()
  const { user, refreshUser } = useAuth()

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword,     setNewPassword]     = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error,           setError]           = useState('')
  const [loading,         setLoading]         = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.')
      return
    }
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (newPassword === currentPassword) {
      setError('New password must be different from your current password.')
      return
    }

    setLoading(true)
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      })
      await refreshUser()
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm space-y-3">
        <div className="bg-white rounded-xl shadow-md border border-amber-200 overflow-hidden">
          <div className="bg-amber-50 border-b border-amber-200 px-6 py-4 text-center">
            <h1 className="text-xl font-bold text-amber-800">Set your password</h1>
            <p className="text-sm text-amber-700 mt-1">
              You must change your password before continuing.
            </p>
          </div>
          <div className="px-6 py-6">
            {user && (
              <p className="text-sm text-gray-500 mb-4">
                Signed in as <span className="font-medium text-gray-700">{user.email}</span>
              </p>
            )}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1">
                <label htmlFor="current" className="block text-sm font-medium text-gray-700">
                  Temporary password
                </label>
                <Input
                  id="current"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="new" className="block text-sm font-medium text-gray-700">
                  New password
                </label>
                <Input
                  id="new"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-1">
                <label htmlFor="confirm" className="block text-sm font-medium text-gray-700">
                  Confirm new password
                </label>
                <Input
                  id="confirm"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
              </div>
              {error && (
                <p className="text-sm text-red-600 rounded bg-red-50 px-3 py-2">{error}</p>
              )}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Saving…' : 'Set password and continue'}
              </Button>
            </form>
          </div>
        </div>
        <p className="text-xs text-center text-gray-400">
          This step is required for account security.
        </p>
      </div>
    </div>
  )
}
