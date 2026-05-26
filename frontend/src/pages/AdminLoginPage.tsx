import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAdminAuth } from '@/lib/adminAuth'
import { getAdminErrorMessage } from '@/lib/adminApi'
import { Shield, Building2, Activity, CreditCard, Lock } from 'lucide-react'

const FEATURES = [
  { icon: Building2, title: 'Manage Universities', desc: 'Provision and oversee all tenant institutions' },
  { icon: Activity,   title: 'Platform Operations', desc: 'Monitor health, uptime, and system metrics' },
  { icon: CreditCard, title: 'Subscriptions & Plans', desc: 'Control licensing and feature access' },
  { icon: Lock,       title: 'Security & Compliance', desc: 'Audit logs, access control, and data governance' },
]

export default function AdminLoginPage() {
  const navigate = useNavigate()
  const auth = useAdminAuth()

  const [email,      setEmail]      = useState('')
  const [password,   setPassword]   = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [error,      setError]      = useState('')
  const [loading,    setLoading]    = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await auth.login(email.trim(), password)
      navigate('/admin/dashboard', { replace: true })
    } catch (err) {
      setError(getAdminErrorMessage(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex" style={{ background: '#060d1f' }}>

      {/* ── Left brand panel ──────────────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[52%] flex-col px-14 py-12 relative overflow-hidden"
        style={{ background: 'linear-gradient(135deg, #060d1f 0%, #080f1e 60%, #0a1428 100%)' }}
      >
        {/* Grid overlay */}
        <div
          className="absolute inset-0 opacity-[0.032]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.6) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.6) 1px, transparent 1px)',
            backgroundSize: '48px 48px',
          }}
        />

        {/* Glow orbs */}
        <div
          className="absolute top-[-80px] right-[-80px] w-[420px] h-[420px] rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.18) 0%, transparent 70%)' }}
        />
        <div
          className="absolute bottom-[-60px] left-[-60px] w-[300px] h-[300px] rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(6,182,212,0.08) 0%, transparent 70%)' }}
        />
        <div
          className="absolute top-[45%] left-[55%] w-[200px] h-[200px] rounded-full"
          style={{ background: 'radial-gradient(circle, rgba(16,185,129,0.07) 0%, transparent 70%)' }}
        />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <img
            src="/branding/sherpavector-logo.png"
            alt="SherpaVector"
            className="h-9 w-9 rounded-full object-contain flex-shrink-0"
            style={{ filter: 'drop-shadow(0 0 8px rgba(16,185,129,0.4))' }}
          />
          <span className="text-slate-200 font-semibold text-base tracking-wide">SherpaVector</span>
        </div>

        {/* Hero */}
        <div className="relative z-10 flex-1 flex flex-col justify-center">
          <div className="mb-5">
            <span className="inline-flex items-center gap-1.5 text-emerald-400 text-[10px] font-bold uppercase tracking-[0.18em] bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
              <Shield className="h-3 w-3" />
              Platform Console
            </span>
          </div>

          <h1 className="text-4xl font-extrabold text-white leading-none tracking-tight mb-2">
            VIDYA <span className="text-emerald-400">AI</span>
          </h1>
          <p className="text-lg font-semibold text-slate-300 mb-2">Platform Console</p>
          <p className="text-sm text-slate-500 mb-8 max-w-sm leading-relaxed">
            AI-powered academic intelligence platform for universities and institutions.
          </p>

          {/* Feature blocks */}
          <div className="grid grid-cols-2 gap-3 max-w-sm">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-xl p-3.5"
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.07)',
                  backdropFilter: 'blur(8px)',
                }}
              >
                <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-2">
                  <Icon className="h-3.5 w-3.5 text-emerald-400" />
                </div>
                <p className="text-xs font-semibold text-slate-200 leading-tight mb-0.5">{title}</p>
                <p className="text-[10px] text-slate-500 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="relative z-10 pt-5" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <p className="text-slate-600 text-xs">© 2026 SherpaVector Pvt. Ltd.</p>
          <p className="text-slate-700 text-[10px] mt-0.5 tracking-wide">VIDYA AI · Platform Console</p>
        </div>
      </div>

      {/* ── Right login panel ─────────────────────────────────────────── */}
      <div
        className="flex-1 flex items-center justify-center px-6 py-12"
        style={{ background: '#080f1e' }}
      >
        <div className="w-full max-w-sm">

          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8 justify-center">
            <img
              src="/branding/sherpavector-logo.png"
              alt="SherpaVector"
              className="h-8 w-8 rounded-full object-contain flex-shrink-0"
            />
            <div>
              <p className="text-sm font-bold text-white leading-none">SherpaVector</p>
              <p className="text-[10px] text-slate-500 mt-0.5">Platform Console</p>
            </div>
          </div>

          {/* Form card */}
          <div
            className="rounded-2xl p-8"
            style={{
              background: 'rgba(12,22,41,0.85)',
              border: '1px solid rgba(255,255,255,0.08)',
              backdropFilter: 'blur(16px)',
            }}
          >
            <div className="mb-7">
              <h2 className="text-xl font-bold text-white">Welcome back,</h2>
              <p className="text-base font-semibold text-emerald-400 mt-0.5">Super Admin</p>
              <p className="text-xs text-slate-500 mt-1.5">Sign in to the Platform Console</p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="email" className="block text-[10px] font-bold text-slate-500 uppercase tracking-[0.12em]">
                  Email address
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@sherpavector.com"
                  required
                  autoFocus
                  className="w-full px-3.5 py-2.5 rounded-lg text-sm text-slate-100 placeholder:text-slate-600 outline-none transition-all"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(16,185,129,0.4)' }}
                  onBlur={(e)  => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)' }}
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="password" className="block text-[10px] font-bold text-slate-500 uppercase tracking-[0.12em]">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="w-full px-3.5 py-2.5 rounded-lg text-sm text-slate-100 placeholder:text-slate-600 outline-none transition-all"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                  onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(16,185,129,0.4)' }}
                  onBlur={(e)  => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)' }}
                />
              </div>

              <label className="flex items-center gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="w-3.5 h-3.5 rounded accent-emerald-500"
                />
                <span className="text-xs text-slate-500">Remember me</span>
              </label>

              {error && (
                <div
                  className="text-xs text-red-400 rounded-lg px-3.5 py-2.5"
                  style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                style={{
                  background: 'linear-gradient(135deg, #10b981, #059669)',
                  boxShadow: '0 0 24px rgba(16,185,129,0.2)',
                }}
              >
                {loading ? 'Signing in…' : 'Sign in to Console'}
              </button>
            </form>

            <div className="mt-6 pt-5" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
              <div className="flex items-center gap-2 justify-center">
                <Lock className="h-3 w-3 text-slate-600 flex-shrink-0" />
                <p className="text-[10px] text-slate-600 text-center">
                  Restricted area · Only authorized Super Admins
                </p>
              </div>
            </div>
          </div>

          <p className="text-[10px] text-center text-slate-700 mt-5">
            SherpaVector Platform Console · Super Admin Access
          </p>
        </div>
      </div>

    </div>
  )
}
