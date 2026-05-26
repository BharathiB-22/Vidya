import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAdminAuth } from '@/lib/adminAuth'
import { getAdminErrorMessage } from '@/lib/adminApi'
import {
  Shield,
  Building2,
  Activity,
  Lock,
  Mail,
  Eye,
  EyeOff,
  Headphones,
  Crown,
  Users,
  BarChart3,
  FileText,
  CheckCircle2,
} from 'lucide-react'

const CAPABILITIES = [
  'Full Platform Control',
  'Institution & User Oversight',
  'Advanced Analytics',
  'System Configuration',
  'Security & Compliance',
  'AI Insights & Reports',
  'Audit Logs & Monitoring',
  'Integrations Management',
]

function GoogleIcon() {
  return (
    <span className="text-lg font-bold">
      <span className="text-blue-500">G</span>
    </span>
  )
}

function HeroVisual() {
  const nodes = [
    { icon: Users, label: 'User & Role\nManagement', className: 'left-[50%] top-[0%] -translate-x-1/2' },
    { icon: Building2, label: 'Institution\nManagement', className: 'right-[2%] top-[28%]' },
    { icon: BarChart3, label: 'System\nAnalytics', className: 'right-[4%] bottom-[24%]' },
    { icon: FileText, label: 'AI Insights &\nReports', className: 'left-[50%] bottom-[0%] -translate-x-1/2' },
    { icon: Shield, label: 'Security &\nCompliance', className: 'left-[4%] bottom-[24%]' },
    { icon: Activity, label: 'Platform\nMonitoring', className: 'left-[2%] top-[28%]' },
  ]

  return (
    <div className="relative mx-auto h-[360px] w-[420px] max-w-full">
      <div className="absolute inset-8 rounded-full border border-emerald-400/20" />
      <div className="absolute inset-20 rounded-full border border-dashed border-emerald-400/20" />

      <div className="absolute left-1/2 top-1/2 z-20 flex h-36 w-36 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-[2rem] border border-emerald-300/50 bg-emerald-400/10 shadow-[0_0_70px_rgba(34,197,94,0.45)] backdrop-blur">
        <div className="flex h-28 w-28 items-center justify-center rounded-[1.5rem] border border-emerald-300/40 bg-slate-950/70">
          <Crown className="h-14 w-14 text-emerald-300" />
        </div>
      </div>

      <div className="absolute left-1/2 top-1/2 h-52 w-52 -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-400/20 blur-3xl" />

      {nodes.map(({ icon: Icon, label, className }) => (
        <div key={label} className={`absolute z-30 text-center ${className}`}>
          <div className="mx-auto mb-2 flex h-14 w-14 items-center justify-center rounded-full border border-emerald-300/40 bg-slate-950/80 shadow-[0_0_25px_rgba(34,197,94,0.25)]">
            <Icon className="h-6 w-6 text-emerald-300" />
          </div>
          <p className="whitespace-pre-line text-[11px] font-medium leading-tight text-white/90">{label}</p>
        </div>
      ))}
    </div>
  )
}

export default function AdminLoginPage() {
  const navigate = useNavigate()
  const auth = useAdminAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [rememberMe, setRememberMe] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [googleLoading, setGoogleLoading] = useState(false)

  useEffect(() => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined
    if (!clientId || !window.google) return

    window.google.accounts.id.initialize({
      client_id: clientId,
      auto_select: false,
      callback: async ({ credential }) => {
        setError('')
        setGoogleLoading(true)
        try {
          await auth.loginWithGoogle(credential)
          navigate('/admin/dashboard', { replace: true })
        } catch (err) {
          setError(getAdminErrorMessage(err))
        } finally {
          setGoogleLoading(false)
        }
      },
    })
  }, []) // auth and navigate are stable refs from context/router

  function handleGoogleSignIn() {
    if (!window.google) {
      setError('Google Sign-In is not available. Please use email and password.')
      return
    }
    setError('')
    window.google.accounts.id.prompt((notification) => {
      if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
        setError('Google Sign-In was dismissed or unavailable. Please use email and password.')
      }
    })
  }

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
    <div className="min-h-screen overflow-hidden bg-slate-50 text-slate-950">
      <div className="grid min-h-screen lg:grid-cols-[55%_45%]">
        <section className="relative hidden overflow-hidden rounded-r-[2rem] bg-[#020b12] px-12 py-10 text-white lg:block">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_40%,rgba(34,197,94,0.18),transparent_32%),radial-gradient(circle_at_30%_90%,rgba(20,184,166,0.16),transparent_35%)]" />
          <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.035)_1px,transparent_1px)] bg-[size:48px_48px] opacity-40" />
          <div className="absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-emerald-950/50 to-transparent" />

          <div className="relative z-10">
            <div className="flex items-center gap-4">
              <img
                src="/branding/sherpavector-logo.png"
                alt="SherpaVector"
                className="h-16 w-16 rounded-full object-contain drop-shadow-[0_0_18px_rgba(34,197,94,0.65)]"
              />
              <div>
                <h1 className="text-3xl font-black tracking-wide">SHERPAVECTOR</h1>
                <p className="text-xs font-semibold tracking-[0.34em] text-white/80">
                  IMAGINE <span className="text-emerald-400">|</span> TRANSFORM <span className="text-emerald-400">|</span> ELEVATE
                </p>
              </div>
            </div>

            <div className="mt-14 inline-flex items-center gap-3 rounded-full border border-emerald-400/40 bg-emerald-400/10 px-6 py-3 text-sm font-bold uppercase tracking-[0.24em] text-emerald-300">
              <Crown className="h-4 w-4" />
              Super Admin Portal
            </div>

            <div className="mt-10 grid grid-cols-[48%_52%] items-center gap-4">
              <div>
                <h2 className="text-6xl font-black leading-[1.05] tracking-tight">
                  Welcome,
                  <br />
                  <span className="bg-gradient-to-r from-emerald-300 to-green-500 bg-clip-text text-transparent">
                    Super Admin
                  </span>
                </h2>
                <p className="mt-6 max-w-sm text-lg leading-8 text-white/85">
                  Access. Control. Empower.
                  <br />
                  Manage your entire ecosystem with intelligence and confidence.
                </p>
              </div>

              <HeroVisual />
            </div>

            <div className="mt-6 max-w-[560px] rounded-2xl border border-white/10 bg-white/[0.06] p-6 shadow-2xl backdrop-blur-xl">
              <h3 className="mb-5 flex items-center gap-3 text-xl font-bold text-emerald-300">
                <Shield className="h-5 w-5" />
                Super Admin Capabilities
              </h3>

              <div className="grid grid-cols-2 gap-4">
                {CAPABILITIES.map((item) => (
                  <div key={item} className="flex items-center gap-3 text-sm text-white/90">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 max-w-[560px] rounded-2xl border border-white/10 bg-white/[0.05] p-5 text-sm text-white/85 backdrop-blur-xl">
              <div className="flex items-center gap-4">
                <Shield className="h-8 w-8 text-white/40" />
                <p>
                  <span className="font-semibold text-white">Enterprise-grade security.</span> Built for scale.
                  <br />
                  Trusted by institutions. Designed for leadership.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section className="relative flex items-center justify-center overflow-hidden px-6 py-10">
          <div className="absolute inset-0 bg-gradient-to-br from-white via-slate-50 to-emerald-50/30" />
          <div className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-emerald-100 blur-3xl" />
          <div className="absolute -bottom-24 -left-24 h-72 w-72 rounded-full bg-sky-100 blur-3xl" />

          <div className="relative z-10 w-full max-w-[560px]">
            <div className="mb-10 flex justify-end">
              <div className="flex items-center gap-3 text-sm">
                <span className="text-slate-600">Need help?</span>
                <Headphones className="h-5 w-5 text-emerald-600" />
                <span className="font-bold text-emerald-700">Support</span>
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-200/80 bg-white/90 p-8 shadow-[0_24px_80px_rgba(15,23,42,0.12)] backdrop-blur-xl sm:p-10">
              <div className="mb-8">
                <h2 className="text-3xl font-black tracking-tight text-slate-950">Welcome back, Super Admin!</h2>
                <p className="mt-2 text-slate-500">Sign in to access your control center</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                <div>
                  <label htmlFor="email" className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-900">
                    <Users className="h-4 w-4" />
                    Admin Email
                  </label>
                  <div className="flex items-center rounded-xl border border-slate-200 bg-white px-4 shadow-sm transition focus-within:border-emerald-400 focus-within:ring-4 focus-within:ring-emerald-100">
                    <Mail className="h-5 w-5 text-emerald-600" />
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="admin@yourdomain.com"
                      required
                      autoFocus
                      className="w-full bg-transparent px-4 py-3 text-sm outline-none placeholder:text-slate-400"
                    />
                  </div>
                </div>

                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <label htmlFor="password" className="flex items-center gap-2 text-sm font-bold text-slate-900">
                      <Lock className="h-4 w-4 text-emerald-700" />
                      Password
                    </label>
                    <button type="button" className="text-xs font-semibold text-emerald-700">
                      Forgot password?
                    </button>
                  </div>

                  <div className="flex items-center rounded-xl border border-slate-200 bg-white px-4 shadow-sm transition focus-within:border-emerald-400 focus-within:ring-4 focus-within:ring-emerald-100">
                    <Lock className="h-5 w-5 text-emerald-600" />
                    <input
                      id="password"
                      type={showPassword ? 'text' : 'password'}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••••••"
                      required
                      className="w-full bg-transparent px-4 py-3 text-sm outline-none placeholder:text-slate-400"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="text-slate-500 hover:text-slate-700"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="mb-2 flex items-center gap-2 text-sm font-bold text-slate-900">
                    <Shield className="h-4 w-4 text-emerald-700" />
                    Two-Factor Authentication
                  </label>
                  <div className="flex items-center rounded-xl border border-slate-200 bg-white px-4 shadow-sm">
                    <Shield className="h-5 w-5 text-emerald-600" />
                    <input
                      type="text"
                      placeholder="Enter 6-digit code"
                      className="w-full bg-transparent px-4 py-3 text-sm outline-none placeholder:text-slate-400"
                    />
                    <button type="button" className="whitespace-nowrap text-xs font-semibold text-emerald-700">
                      Resend code
                    </button>
                  </div>
                </div>

                <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-600">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-300 accent-emerald-600"
                  />
                  Remember me
                </label>

                {error && (
                  <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-700 to-emerald-500 px-5 py-3.5 text-base font-bold text-white shadow-[0_18px_35px_rgba(16,185,129,0.28)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? 'Signing in…' : 'Sign in'}
                </button>

                <div className="flex items-center gap-4 py-1">
                  <div className="h-px flex-1 bg-slate-200" />
                  <span className="text-xs font-semibold text-slate-400">OR</span>
                  <div className="h-px flex-1 bg-slate-200" />
                </div>

                <button
                  type="button"
                  onClick={handleGoogleSignIn}
                  disabled={googleLoading || loading}
                  className="flex w-full items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-800 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <GoogleIcon />
                  {googleLoading ? 'Signing in with Google…' : 'Sign in with Google'}
                </button>
              </form>

              <div className="mt-8 flex items-center justify-center gap-5 border-t border-slate-100 pt-6 text-xs font-medium text-slate-500">
                <span className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-emerald-600" />
                  Secure
                </span>
                <span>•</span>
                <span className="flex items-center gap-2">
                  <Lock className="h-4 w-4 text-emerald-600" />
                  Encrypted
                </span>
                <span>•</span>
                <span className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-emerald-600" />
                  Trusted
                </span>
              </div>
            </div>

            <div className="mt-8 flex items-center justify-between gap-4 text-xs text-slate-500">
              <div>
                <p>© 2026 SherpaVector Pvt. Ltd. All rights reserved.</p>
                <p className="mt-1">VIDYA AI • Enterprise Academic Platform</p>
              </div>

              <div className="flex items-center gap-3">
                <img
                  src="/branding/sherpavector-logo.png"
                  alt="SherpaVector"
                  className="h-12 w-12 rounded-full object-contain"
                />
                <div>
                  <p className="text-xl font-black text-slate-950">SHERPAVECTOR</p>
                  <p className="text-[9px] font-bold tracking-[0.22em] text-slate-500">
                    IMAGINE | TRANSFORM | ELEVATE
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}