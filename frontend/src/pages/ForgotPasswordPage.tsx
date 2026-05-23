import { useState } from 'react'
import { Link } from 'react-router-dom'
import api, { getErrorMessage } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

type Step = 'request' | 'verify' | 'confirm' | 'done'

export default function ForgotPasswordPage() {
  const [step,         setStep]         = useState<Step>('request')
  const [slug,         setSlug]         = useState(localStorage.getItem('vidya_tenant_slug') ?? '')
  const [email,        setEmail]        = useState('')
  const [otp,          setOtp]          = useState('')
  const [resetToken,   setResetToken]   = useState('')
  const [newPassword,  setNewPassword]  = useState('')
  const [confirmPw,    setConfirmPw]    = useState('')
  const [error,        setError]        = useState('')
  const [loading,      setLoading]      = useState(false)

  function applySlug(s: string) {
    localStorage.setItem('vidya_tenant_slug', s)
  }

  async function handleRequest(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    applySlug(slug.trim())
    try {
      await api.post('/auth/password-reset/request', { email: email.trim() })
      setStep('verify')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleVerify(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const { data } = await api.post('/auth/password-reset/verify', {
        email: email.trim(),
        otp: otp.trim(),
      })
      setResetToken(data.reset_token)
      setStep('confirm')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (newPassword !== confirmPw) {
      setError('Passwords do not match.')
      return
    }
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setLoading(true)
    try {
      await api.post('/auth/password-reset/confirm', {
        reset_token: resetToken,
        new_password: newPassword,
      })
      setStep('done')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm space-y-3">
        <div className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">

          {/* Header */}
          <div className="px-6 pt-6 pb-2 text-center">
            <h1 className="text-2xl font-bold text-indigo-700">Vidya</h1>
            <p className="text-sm text-gray-500 mt-1">
              {step === 'done' ? 'Password reset' : 'Reset your password'}
            </p>
          </div>

          <div className="px-6 pb-6">

            {/* Step 1 — enter slug + email */}
            {step === 'request' && (
              <form onSubmit={handleRequest} className="space-y-4 mt-4">
                <div className="space-y-1">
                  <label htmlFor="slug" className="block text-sm font-medium text-gray-700">
                    Institution slug
                  </label>
                  <Input
                    id="slug"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="e.g. my-university"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                    Email
                  </label>
                  <Input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@university.edu"
                    required
                    autoFocus
                  />
                </div>
                {error && (
                  <p className="text-sm text-red-600 rounded bg-red-50 px-3 py-2">{error}</p>
                )}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Sending…' : 'Send reset code'}
                </Button>
              </form>
            )}

            {/* Step 2 — enter OTP */}
            {step === 'verify' && (
              <form onSubmit={handleVerify} className="space-y-4 mt-4">
                <p className="text-sm text-gray-600 bg-blue-50 rounded px-3 py-2 border border-blue-100">
                  A one-time code has been sent to <strong>{email}</strong>.
                  Check your email or ask your system administrator.
                </p>
                <div className="space-y-1">
                  <label htmlFor="otp" className="block text-sm font-medium text-gray-700">
                    Reset code (OTP)
                  </label>
                  <Input
                    id="otp"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value)}
                    placeholder="6-digit code"
                    required
                    autoFocus
                    maxLength={10}
                  />
                </div>
                {error && (
                  <p className="text-sm text-red-600 rounded bg-red-50 px-3 py-2">{error}</p>
                )}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Verifying…' : 'Verify code'}
                </Button>
                <button
                  type="button"
                  className="w-full text-xs text-gray-400 hover:text-gray-600 mt-1"
                  onClick={() => { setStep('request'); setError('') }}
                >
                  Resend code
                </button>
              </form>
            )}

            {/* Step 3 — set new password */}
            {step === 'confirm' && (
              <form onSubmit={handleConfirm} className="space-y-4 mt-4">
                <div className="space-y-1">
                  <label htmlFor="newpw" className="block text-sm font-medium text-gray-700">
                    New password
                  </label>
                  <Input
                    id="newpw"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="confirmpw" className="block text-sm font-medium text-gray-700">
                    Confirm new password
                  </label>
                  <Input
                    id="confirmpw"
                    type="password"
                    value={confirmPw}
                    onChange={(e) => setConfirmPw(e.target.value)}
                    required
                  />
                </div>
                {error && (
                  <p className="text-sm text-red-600 rounded bg-red-50 px-3 py-2">{error}</p>
                )}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Saving…' : 'Set new password'}
                </Button>
              </form>
            )}

            {/* Done */}
            {step === 'done' && (
              <div className="mt-4 space-y-4 text-center">
                <p className="text-sm text-green-700 bg-green-50 rounded px-3 py-3 border border-green-200">
                  Your password has been reset. You can now sign in with your new password.
                </p>
                <Link
                  to="/login"
                  className="block w-full text-center px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors"
                >
                  Back to sign in
                </Link>
              </div>
            )}

          </div>
        </div>

        <p className="text-xs text-center text-gray-400">
          <Link to="/login" className="hover:text-gray-600 underline underline-offset-2">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
