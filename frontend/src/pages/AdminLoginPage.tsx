import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAdminAuth } from '@/lib/adminAuth'
import { getAdminErrorMessage } from '@/lib/adminApi'
import { Shield, Building2, Activity, CreditCard, Lock, Cpu } from 'lucide-react'

const FEATURES = [
  { icon: Building2, title: 'Manage Universities',  desc: 'Provision and oversee all tenant institutions' },
  { icon: Activity,  title: 'Platform Operations',  desc: 'Monitor health, uptime, and system metrics'    },
  { icon: CreditCard,title: 'Subscriptions & Plans',desc: 'Control licensing and feature access'           },
  { icon: Lock,      title: 'Security & Compliance',desc: 'Audit logs, access control, and data governance'},
]

// ── Central AI-network node diagram — pure CSS + inline SVG, no external assets ──
function HeroVisual() {
  return (
    <div className="relative mx-auto flex-shrink-0" style={{ width: 188, height: 188 }}>

      {/* SVG layer: rings + connection lines + corner accents */}
      <svg className="absolute inset-0 w-full h-full" viewBox="0 0 188 188" fill="none">
        {/* Ambient outer ring */}
        <circle cx="94" cy="94" r="86" stroke="rgba(16,185,129,0.05)" strokeWidth="1" />
        {/* Middle dashed ring */}
        <circle cx="94" cy="94" r="58" stroke="rgba(16,185,129,0.08)" strokeWidth="1" strokeDasharray="4 4" />
        {/* Inner ring */}
        <circle cx="94" cy="94" r="33" stroke="rgba(16,185,129,0.14)" strokeWidth="1" />

        {/* Radial spokes from center to each satellite */}
        <line x1="94" y1="94" x2="94"  y2="20"  stroke="rgba(16,185,129,0.22)" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="94" y1="94" x2="168" y2="94"  stroke="rgba(16,185,129,0.22)" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="94" y1="94" x2="94"  y2="168" stroke="rgba(16,185,129,0.22)" strokeWidth="1" strokeDasharray="3 3" />
        <line x1="94" y1="94" x2="20"  y2="94"  stroke="rgba(16,185,129,0.22)" strokeWidth="1" strokeDasharray="3 3" />

        {/* Corner accent ticks */}
        <line x1="10" y1="10" x2="24" y2="24" stroke="rgba(16,185,129,0.12)" strokeWidth="1" />
        <line x1="178" y1="10" x2="164" y2="24" stroke="rgba(16,185,129,0.12)" strokeWidth="1" />
        <line x1="10" y1="178" x2="24" y2="164" stroke="rgba(16,185,129,0.12)" strokeWidth="1" />
        <line x1="178" y1="178" x2="164" y2="164" stroke="rgba(16,185,129,0.12)" strokeWidth="1" />
        <circle cx="10"  cy="10"  r="1.5" fill="rgba(16,185,129,0.2)" />
        <circle cx="178" cy="10"  r="1.5" fill="rgba(16,185,129,0.2)" />
        <circle cx="10"  cy="178" r="1.5" fill="rgba(16,185,129,0.2)" />
        <circle cx="178" cy="178" r="1.5" fill="rgba(16,185,129,0.2)" />
      </svg>

      {/* Centre AI node */}
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[52px] h-[52px] rounded-full flex items-center justify-center z-10"
        style={{
          background: 'radial-gradient(circle, rgba(16,185,129,0.28) 0%, rgba(6,182,212,0.1) 65%, transparent 100%)',
          border: '1px solid rgba(16,185,129,0.5)',
          boxShadow: '0 0 22px rgba(16,185,129,0.32), 0 0 44px rgba(16,185,129,0.1), inset 0 0 14px rgba(16,185,129,0.1)',
        }}
      >
        <Cpu className="h-5 w-5 text-emerald-300" />
      </div>

      {/* Satellite nodes — same icons as FEATURES list */}
      {/* Top — Building2: center at (94,20), box: left=76, top=2 */}
      <div className="absolute z-10 w-9 h-9 rounded-full flex items-center justify-center"
           style={{ left: 76, top: 2, background: 'rgba(5,12,22,0.95)', border: '1px solid rgba(16,185,129,0.28)', boxShadow: '0 0 8px rgba(16,185,129,0.18)' }}>
        <Building2 className="h-[15px] w-[15px] text-emerald-500" />
      </div>
      {/* Right — Activity: center at (168,94), box: left=150, top=76 */}
      <div className="absolute z-10 w-9 h-9 rounded-full flex items-center justify-center"
           style={{ left: 150, top: 76, background: 'rgba(5,12,22,0.95)', border: '1px solid rgba(16,185,129,0.28)', boxShadow: '0 0 8px rgba(16,185,129,0.18)' }}>
        <Activity className="h-[15px] w-[15px] text-emerald-500" />
      </div>
      {/* Bottom — CreditCard: center at (94,168), box: left=76, top=150 */}
      <div className="absolute z-10 w-9 h-9 rounded-full flex items-center justify-center"
           style={{ left: 76, top: 150, background: 'rgba(5,12,22,0.95)', border: '1px solid rgba(16,185,129,0.28)', boxShadow: '0 0 8px rgba(16,185,129,0.18)' }}>
        <CreditCard className="h-[15px] w-[15px] text-emerald-500" />
      </div>
      {/* Left — Lock: center at (20,94), box: left=2, top=76 */}
      <div className="absolute z-10 w-9 h-9 rounded-full flex items-center justify-center"
           style={{ left: 2, top: 76, background: 'rgba(5,12,22,0.95)', border: '1px solid rgba(16,185,129,0.28)', boxShadow: '0 0 8px rgba(16,185,129,0.18)' }}>
        <Lock className="h-[15px] w-[15px] text-emerald-500" />
      </div>

    </div>
  )
}

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
    <div className="min-h-screen flex" style={{ background: '#010608' }}>

      {/* ── Left hero panel ──────────────────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[52%] flex-col px-14 py-10 relative overflow-hidden"
        style={{ background: 'linear-gradient(150deg, #010608 0%, #03090f 45%, #050e18 100%)' }}
      >

        {/* ── Background layers ──────────────────────────────────────── */}

        {/* Fine grid */}
        <div
          className="absolute inset-0 opacity-[0.028]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.7) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.7) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
        />

        {/* Emerald ambient glow — top-right */}
        <div
          className="absolute pointer-events-none"
          style={{
            top: -120, right: -100,
            width: 480, height: 480,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(16,185,129,0.16) 0%, rgba(16,185,129,0.04) 50%, transparent 70%)',
          }}
        />
        {/* Cyan ambient glow — bottom-left */}
        <div
          className="absolute pointer-events-none"
          style={{
            bottom: -80, left: -80,
            width: 320, height: 320,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(6,182,212,0.1) 0%, transparent 65%)',
          }}
        />
        {/* Mid-panel subtle glow */}
        <div
          className="absolute pointer-events-none"
          style={{
            top: '42%', left: '48%',
            width: 240, height: 240,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(16,185,129,0.06) 0%, transparent 70%)',
          }}
        />

        {/* Circuit trace decorations */}
        {/* Top-right L-trace */}
        <div className="absolute pointer-events-none" style={{ top: '7%', right: '12%', width: 1, height: '14%', background: 'linear-gradient(to bottom, transparent, rgba(16,185,129,0.14))' }} />
        <div className="absolute pointer-events-none" style={{ top: '21%', right: '12%', width: '9%', height: 1, background: 'linear-gradient(to right, rgba(16,185,129,0.14), transparent)' }} />
        <div className="absolute w-1.5 h-1.5 rounded-full pointer-events-none" style={{ top: 'calc(21% - 3px)', right: 'calc(21% - 3px)', background: 'rgba(16,185,129,0.22)' }} />
        {/* Bottom-left L-trace */}
        <div className="absolute pointer-events-none" style={{ bottom: '14%', left: '10%', width: '8%', height: 1, background: 'linear-gradient(to right, transparent, rgba(6,182,212,0.12))' }} />
        <div className="absolute pointer-events-none" style={{ bottom: '9%', left: 'calc(18% - 1px)', width: 1, height: '5%', background: 'linear-gradient(to bottom, rgba(6,182,212,0.12), transparent)' }} />
        <div className="absolute w-1 h-1 rounded-full pointer-events-none" style={{ bottom: 'calc(14% - 2px)', left: 'calc(18% - 2px)', background: 'rgba(6,182,212,0.2)' }} />
        {/* Right-edge horizontal trace */}
        <div className="absolute pointer-events-none" style={{ top: '55%', right: '5%', width: '7%', height: 1, background: 'linear-gradient(to left, transparent, rgba(16,185,129,0.1))' }} />
        <div className="absolute w-1 h-1 rounded-full pointer-events-none" style={{ top: 'calc(55% - 2px)', right: 'calc(12% - 2px)', background: 'rgba(16,185,129,0.18)' }} />

        {/* ── Logo ────────────────────────────────────────────────── */}
        <div className="relative z-10 flex items-center gap-3">
          <img
            src="/branding/sherpavector-logo.png"
            alt="SherpaVector"
            className="h-9 w-9 rounded-full object-contain flex-shrink-0"
            style={{ filter: 'drop-shadow(0 0 8px rgba(16,185,129,0.45))' }}
          />
          <span className="text-slate-300 font-semibold text-base tracking-wide">SherpaVector</span>
        </div>

        {/* ── Hero content ────────────────────────────────────────── */}
        <div className="relative z-10 flex-1 flex flex-col justify-center">

          {/* Platform Console badge */}
          <div className="mb-4">
            <span className="inline-flex items-center gap-1.5 text-emerald-400 text-[10px] font-bold uppercase tracking-[0.18em] bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
              <Shield className="h-3 w-3" />
              Platform Console
            </span>
          </div>

          {/* Product headline */}
          <h1 className="text-[42px] font-extrabold text-white leading-none tracking-tight mb-1">
            VIDYA <span className="text-emerald-400">AI</span>
          </h1>
          <p className="text-base font-semibold text-slate-400 mb-1">Platform Console</p>
          <p className="text-sm text-slate-600 mb-6 leading-relaxed">
            AI-powered academic intelligence platform for universities and institutions.
          </p>

          {/* Central node diagram */}
          <HeroVisual />

          {/* Feature blocks */}
          <div className="grid grid-cols-2 gap-2.5 mt-6">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-xl p-3"
                style={{
                  background: 'rgba(255,255,255,0.025)',
                  border: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <div
                  className="w-6 h-6 rounded-md flex items-center justify-center mb-1.5"
                  style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}
                >
                  <Icon className="h-3 w-3 text-emerald-400" />
                </div>
                <p className="text-[11px] font-semibold text-slate-300 leading-tight mb-0.5">{title}</p>
                <p className="text-[10px] text-slate-600 leading-snug">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Footer ──────────────────────────────────────────────── */}
        <div className="relative z-10 pt-4" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          <p className="text-slate-600 text-xs">© 2026 SherpaVector Pvt. Ltd.</p>
          <p className="text-slate-700 text-[10px] mt-0.5 tracking-wide">VIDYA AI · Platform Console</p>
        </div>

      </div>

      {/* ── Right login panel ────────────────────────────────────────────── */}
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
