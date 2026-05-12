import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getErrorMessage } from '@/lib/api'

const DEMO_USERS = [
  { label: 'Faculty', email: 'faculty@demo-university.edu', password: 'Demo1234!' },
  { label: 'Dean',    email: 'dean@demo-university.edu',    password: 'Demo1234!' },
  { label: 'Admin',   email: 'admin@demo-university.edu',   password: 'Demo1234!' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const auth = useAuth()

  const [slug,     setSlug]     = useState(localStorage.getItem('vidya_tenant_slug') ?? 'demo-university')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  function fillDemo(user: (typeof DEMO_USERS)[number]) {
    setSlug('demo-university')
    setEmail(user.email)
    setPassword(user.password)
    setError('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await auth.login(slug.trim(), email.trim(), password)
      navigate('/programs', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-sm space-y-4">
        {/* Login card */}
        <div className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">
          <div className="px-6 pt-6 pb-2 text-center">
            <h1 className="text-2xl font-bold text-indigo-700">Vidya</h1>
            <p className="text-sm text-gray-500 mt-1">Academic Management Platform</p>
          </div>
          <div className="px-6 pb-6">
            <form onSubmit={handleSubmit} className="space-y-4 mt-4">
              <div className="space-y-1">
                <label htmlFor="slug" className="block text-sm font-medium text-gray-700">
                  Institution slug
                </label>
                <Input
                  id="slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="demo-university"
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
              <div className="space-y-1">
                <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                  Password
                </label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
              {error && (
                <p className="text-sm text-red-600 rounded bg-red-50 px-3 py-2">{error}</p>
              )}
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>
          </div>
        </div>

        {/* Demo quick-fill */}
        <div className="bg-indigo-50 border border-indigo-100 rounded-xl px-4 py-3 space-y-2">
          <p className="text-xs font-semibold text-indigo-700 uppercase tracking-wide">
            Demo — click to fill
          </p>
          <div className="flex gap-2">
            {DEMO_USERS.map((u) => (
              <button
                key={u.label}
                type="button"
                onClick={() => fillDemo(u)}
                className="flex-1 text-xs py-1.5 rounded border border-indigo-200 bg-white text-indigo-700 hover:bg-indigo-100 transition-colors"
              >
                {u.label}
              </button>
            ))}
          </div>
          <p className="text-xs text-indigo-500">Password for all: Demo1234!</p>
        </div>
      </div>
    </div>
  )
}
