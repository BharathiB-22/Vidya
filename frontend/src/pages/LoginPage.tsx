import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getErrorMessage } from '@/lib/api'
import { CheckCircle2, Shield, Sparkles } from 'lucide-react'

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
    <div className="min-h-screen flex bg-[#f6f9ff]">

      {/* ── Left brand panel ─────────────────────────────────────────── */}
      <div className="hidden lg:flex lg:w-[45%] flex-col px-12 py-12 relative overflow-hidden bg-gradient-to-br from-[#071a34] via-sv-dark to-[#06162d] text-white">
        {/* Subtle dot-grid + network texture */}
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)',
            backgroundSize: '26px 26px',
          }}
        />
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(34,211,238,0.35) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.35) 1px, transparent 1px)',
            backgroundSize: '56px 56px',
          }}
        />
        {/* Ambient glows */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-sv-primary/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
        <div className="absolute top-1/4 right-1/3 w-72 h-72 bg-sv-accent/15 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-72 h-72 bg-sv-accent/10 rounded-full blur-3xl translate-y-1/3 -translate-x-1/3" />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <img
            src="/branding/sherpavector-logo.png"
            alt="VIDYA AI"
            className="h-10 w-10 rounded-xl object-contain drop-shadow-[0_0_18px_rgba(16,185,129,0.55)]"
          />
          <span className="text-slate-200 font-semibold text-base tracking-wide">VIDYA AI</span>
        </div>

        {/* Hero copy */}
        <div className="relative z-10 flex-1 flex flex-col justify-center">
          <div className="mb-4">
            <span className="inline-flex items-center gap-2 rounded-full border border-sv-accent/25 bg-sv-accent/10 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-sv-accent shadow-[0_0_24px_rgba(34,211,238,0.10)]">
              <Sparkles className="h-4 w-4" />
              AI-Powered Academic Intelligence
            </span>
          </div>

          <div className="mb-6">
            <h1 className="flex items-baseline gap-3 text-6xl font-extrabold leading-none tracking-tighter">
              <span className="text-white drop-shadow-[0_0_18px_rgba(255,255,255,0.08)]">VIDYA</span>
              <span className="text-[26px] font-black tracking-[0.16em] uppercase text-sv-primary drop-shadow-[0_0_20px_rgba(37,99,235,0.35)]">
                AI
              </span>
            </h1>
            <p className="mt-4 text-slate-300 text-base leading-relaxed max-w-xs">
              The intelligent academic management platform built for modern universities and institutions.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {FEATURES.map((f) => (
              <div
                key={f}
                className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm shadow-[0_10px_30px_rgba(0,0,0,0.18)]"
              >
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl border border-sv-accent/20 bg-sv-accent/10 shadow-[0_0_24px_rgba(34,211,238,0.10)]">
                    <CheckCircle2 className="h-5 w-5 text-sv-accent" />
                  </div>
                  <p className="text-sm font-semibold leading-5 text-slate-100">{f}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom brand footer */}
        <div className="relative z-10 pt-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-200 shadow-[0_0_40px_rgba(16,185,129,0.08)]">
            <Shield className="h-4 w-4 text-sv-accent" />
            Trusted by institutions. Designed for leadership.
          </div>
          <div className="mt-6 border-t border-white/10 pt-6">
            <p className="text-slate-400 text-xs">© 2026 VIDYA AI Academic Platform. All rights reserved.</p>
            <p className="text-slate-500 text-[10px] mt-0.5 font-medium tracking-wide uppercase">
              Powered by VIDYA AI
            </p>
          </div>
        </div>
      </div>

      {/* ── Right login panel ────────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center bg-[#f6f9ff] px-6 py-12">
        <div className="w-full max-w-sm relative">
          {/* Subtle premium background sheen */}
          <div className="pointer-events-none absolute inset-0 -z-10 rounded-[2rem] bg-[radial-gradient(circle_at_20%_10%,rgba(37,99,235,0.10),transparent_40%),radial-gradient(circle_at_80%_30%,rgba(16,185,129,0.08),transparent_45%)]" />

          {/* Mobile-only logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8 justify-center">
            <img
              src="/branding/sherpavector-logo.png"
              alt="VIDYA AI"
              className="h-9 w-9 rounded-xl object-contain drop-shadow-[0_0_14px_rgba(16,185,129,0.35)]"
            />
            <div>
              <p className="text-sm font-bold text-gray-900 leading-none">VIDYA AI</p>
              <p className="text-[10px] text-gray-400 mt-0.5">Academic AI Workspace</p>
            </div>
          </div>

          {/* Form card */}
          <div className="relative bg-white/95 rounded-[1.75rem] shadow-[0_18px_60px_rgba(2,6,23,0.10)] border border-slate-200/70 p-8 overflow-hidden">
            <div className="pointer-events-none absolute inset-0 opacity-[0.55] bg-[radial-gradient(circle_at_10%_0%,rgba(16,185,129,0.10),transparent_35%),radial-gradient(circle_at_90%_20%,rgba(37,99,235,0.12),transparent_40%)]" />
            <div className="relative">
              <div className="mb-6">
                <h2 className="text-2xl font-black tracking-tight text-slate-950">Welcome back</h2>
                <p className="text-sm text-slate-500 mt-1">Sign in to your institution's workspace</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label htmlFor="slug" className="block text-sm font-semibold text-slate-700">
                    Institution ID
                  </label>
                  <Input
                    id="slug"
                    value={slug}
                    onChange={(e) => setSlug(e.target.value)}
                    placeholder="e.g. my-university"
                    required
                    className="h-11 rounded-xl border-slate-200 bg-white/90 px-4 focus-visible:ring-sv-accent focus-visible:ring-2 focus-visible:ring-offset-0"
                  />
                  <p className="text-xs text-slate-400">Your institution's unique identifier</p>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="email" className="block text-sm font-semibold text-slate-700">
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
                    className="h-11 rounded-xl border-slate-200 bg-white/90 px-4 focus-visible:ring-sv-accent focus-visible:ring-2 focus-visible:ring-offset-0"
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3">
                    <label htmlFor="password" className="block text-sm font-semibold text-slate-700">
                      Password
                    </label>
                    <Link
                      to="/forgot-password"
                      className="text-xs font-semibold text-sv-primary hover:text-blue-700 hover:underline"
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
                    className="h-11 rounded-xl border-slate-200 bg-white/90 px-4 focus-visible:ring-sv-accent focus-visible:ring-2 focus-visible:ring-offset-0"
                  />
                </div>

                {error && (
                  <div className="flex items-start gap-2 text-sm text-red-700 rounded-xl bg-red-50 px-3.5 py-2.5 border border-red-100">
                    <span className="mt-0.5 flex-shrink-0">⚠</span>
                    <span>{error}</span>
                  </div>
                )}

                <Button
                  type="submit"
                  className="w-full h-11 rounded-2xl bg-sv-primary hover:bg-blue-700 text-white font-semibold shadow-[0_14px_40px_rgba(37,99,235,0.22)] focus-visible:ring-2 focus-visible:ring-sv-accent focus-visible:ring-offset-0"
                  disabled={loading}
                >
                  {loading ? 'Signing in…' : 'Sign in'}
                </Button>
              </form>

              <div className="mt-6 rounded-xl border border-sv-accent/20 bg-sv-accent/5 p-4">
                <div className="flex items-start gap-3">
                  <Shield className="h-5 w-5 text-sv-accent mt-0.5" />
                  <div className="text-xs leading-relaxed">
                    <span className="font-semibold text-slate-800">Secure access</span> for authorized administrators only.
                    <br />
                    <span className="text-slate-500">All activities are monitored and encrypted.</span>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-5 border-t border-slate-200/70">
                <p className="text-xs text-center text-slate-500">
                  Don't know your Institution ID?{' '}
                  <span className="text-slate-700 font-semibold">Contact your administrator.</span>
                </p>
              </div>
            </div>
          </div>

          <p className="text-xs text-center text-gray-400 mt-4">
            Powered by VIDYA AI
          </p>
        </div>
      </div>

    </div>
  )
}
