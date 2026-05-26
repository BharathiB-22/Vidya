import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getErrorMessage } from '@/lib/api'
import { CheckCircle2, Brain } from 'lucide-react'

const FEATURES = [
  'AI-Assisted Exam Setting & Board Review',
  'Research Supervision & Viva Management',
  'Multi-Tenant Schema-per-Institution SaaS',
  'Bell Curve Grade Analytics Dashboard',
  'NAAC Compliance & Outcome Mapping',
  'Role-Based Access Control (7 Roles)',
]

export default function LoginPage() {
  const navigate = useNavigate()
  const auth = useAuth()

  const [slug,     setSlug]     = useState(localStorage.getItem('vidya_tenant_slug') ?? '')
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await auth.login(slug.trim(), email.trim(), password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">

      {/* ── Left brand panel ─────────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[45%] bg-sv-dark flex-col px-12 py-12 relative overflow-hidden">
        {/* Subtle dot-grid texture */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)',
            backgroundSize: '24px 24px',
          }}
        />
        {/* Ambient glows */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-sv-primary/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute bottom-0 left-0 w-72 h-72 bg-sv-accent/10 rounded-full blur-3xl translate-y-1/3 -translate-x-1/3" />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-9 h-9 bg-sv-primary rounded-xl flex items-center justify-center shadow-lg shadow-sv-primary/30">
            <span className="text-white font-extrabold text-sm tracking-tight">SV</span>
          </div>
          <span className="text-slate-200 font-semibold text-base tracking-wide">SherpaVector</span>
        </div>

        {/* Hero copy */}
        <div className="relative z-10 flex-1 flex flex-col justify-center">
          <div className="mb-4">
            <span className="inline-flex items-center gap-1.5 text-sv-accent text-[11px] font-semibold uppercase tracking-[0.15em] bg-sv-accent/10 px-3 py-1 rounded-full border border-sv-accent/20">
              <Brain className="h-3 w-3" />
              AI-Powered University ERP
            </span>
          </div>

          <h1 className="text-6xl font-extrabold text-white leading-none tracking-tighter mb-1">
            VIDYA
          </h1>
          <p className="text-xl font-bold text-sv-primary mb-5 tracking-widest uppercase">
            ERP AI
          </p>
          <p className="text-slate-400 text-base leading-relaxed mb-10 max-w-xs">
            The intelligent academic management platform built for modern universities and institutions.
          </p>

          <ul className="space-y-3.5">
            {FEATURES.map((f) => (
              <li key={f} className="flex items-center gap-3">
                <CheckCircle2 className="h-4 w-4 text-sv-accent flex-shrink-0" />
                <span className="text-slate-300 text-sm">{f}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Bottom brand footer */}
        <div className="relative z-10 pt-6 border-t border-white/5">
          <p className="text-slate-600 text-xs">© 2026 SherpaVector Pvt. Ltd. All rights reserved.</p>
          <p className="text-slate-700 text-[10px] mt-0.5 font-medium tracking-wide uppercase">
            Enterprise Academic Management Platform
          </p>
        </div>
      </div>

      {/* ── Right login panel ────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center bg-gray-50 px-6 py-12">
        <div className="w-full max-w-sm">

          {/* Mobile-only logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8 justify-center">
            <div className="w-8 h-8 bg-sv-primary rounded-xl flex items-center justify-center">
              <span className="text-white font-extrabold text-xs">SV</span>
            </div>
            <div>
              <p className="text-sm font-bold text-gray-900 leading-none">VIDYA ERP AI</p>
              <p className="text-[10px] text-gray-400 mt-0.5">by SherpaVector</p>
            </div>
          </div>

          {/* Form card */}
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-gray-900">Welcome back</h2>
              <p className="text-sm text-gray-500 mt-1">Sign in to your institution's workspace</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="slug" className="block text-sm font-medium text-gray-700">
                  Institution ID
                </label>
                <Input
                  id="slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  placeholder="e.g. my-university"
                  required
                />
                <p className="text-xs text-gray-400">Your institution's unique identifier</p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="email" className="block text-sm font-medium text-gray-700">
                  Email address
                </label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@institution.edu"
                  required
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <label htmlFor="password" className="block text-sm font-medium text-gray-700">
                    Password
                  </label>
                  <Link
                    to="/forgot-password"
                    className="text-xs text-sv-primary hover:text-blue-700 hover:underline font-medium"
                  >
                    Forgot password?
                  </Link>
                </div>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              {error && (
                <div className="flex items-start gap-2 text-sm text-red-700 rounded-lg bg-red-50 px-3.5 py-2.5 border border-red-100">
                  <span className="mt-0.5 flex-shrink-0">⚠</span>
                  <span>{error}</span>
                </div>
              )}

              <Button
                type="submit"
                className="w-full bg-sv-primary hover:bg-blue-700 text-white font-semibold h-10"
                disabled={loading}
              >
                {loading ? 'Signing in…' : 'Sign in'}
              </Button>
            </form>

            <div className="mt-6 pt-5 border-t border-gray-100">
              <p className="text-xs text-center text-gray-400">
                Don't know your Institution ID?{' '}
                <span className="text-gray-500 font-medium">Contact your administrator.</span>
              </p>
            </div>
          </div>

          <p className="text-xs text-center text-gray-400 mt-4">
            VIDYA ERP AI · SherpaVector · Enterprise Academic Platform
          </p>
        </div>
      </div>

    </div>
  )
}
