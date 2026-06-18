import { useState, useEffect, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getErrorMessage } from '@/lib/api'
import {
  GraduationCap,
  CalendarDays,
  BookOpen,
  ClipboardCheck,
  Microscope,
  BarChart3,
  Shield,
  Lock,
  Eye,
  Users,
  Sparkles,
  Building2,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react'
import axios from 'axios'

interface TenantBranding {
  name: string
  logo_url: string | null
  primary_color: string | null
  secondary_color: string | null
}

const FEATURES = [
  {
    icon: GraduationCap,
    title: 'Student Information System',
    desc: 'Enrolment, profiles, academic records and progression — all in one place.',
  },
  {
    icon: CalendarDays,
    title: 'Attendance & Timetable',
    desc: 'Live attendance tracking, smart scheduling, and faculty timetable management.',
  },
  {
    icon: BookOpen,
    title: 'AI Learning Materials',
    desc: 'Generate syllabi, course kits, and learning packs with Gemini-powered AI.',
  },
  {
    icon: ClipboardCheck,
    title: 'Examination & Results',
    desc: 'AI-assisted question setting, sealed papers, bell-curve grading and results.',
  },
  {
    icon: Microscope,
    title: 'Research & Viva',
    desc: 'End-to-end research supervision, milestone tracking and viva scheduling.',
  },
  {
    icon: BarChart3,
    title: 'Academic Analytics',
    desc: 'NAAC outcome mapping, cohort analytics and governance dashboards for leadership.',
  },
]

const TRUST_ITEMS = [
  { icon: Shield,        label: 'Secure multi-tenant platform' },
  { icon: Users,         label: 'Role-based access control'    },
  { icon: Eye,           label: 'Audit-monitored activity'     },
  { icon: Sparkles,      label: 'AI-assisted workflows'        },
]

const DEFAULT_PRIMARY = '#2563eb'
const DEFAULT_ACCENT  = '#06b6d4'

// ── Contrast helpers ────────────────────────────────────────────────────────
// WCAG 2.1 relative luminance from a 6-digit hex string.
function hexLuminance(hex: string): number {
  const h = hex.replace('#', '')
  if (h.length !== 6) return 0
  const r = parseInt(h.slice(0, 2), 16) / 255
  const g = parseInt(h.slice(2, 4), 16) / 255
  const b = parseInt(h.slice(4, 6), 16) / 255
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

// Returns true when the color is light enough to need dark text on top of it.
function isLight(hex: string): boolean {
  return hexLuminance(hex) > 0.179
}

function classifyError(raw: string): string {
  const lower = raw.toLowerCase()
  if (lower.includes('server encountered') || lower.includes('temporarily unavailable') || lower.includes('try again in a moment'))
    return 'System temporarily unavailable. Please try again in a moment.'
  if (lower.includes('unable to reach') || lower.includes('check your connection'))
    return 'Unable to reach the server. Check your internet connection and try again.'
  if (lower.includes('workspace') || lower.includes('tenant not found') || lower.includes('not found'))
    return 'Invalid workspace. Check your university workspace ID and try again.'
  if (lower.includes('inactive') || lower.includes('disabled'))
    return 'Your account is inactive. Contact your university administrator.'
  if (lower.includes('archived') || lower.includes('deleted') || lower.includes('permanently'))
    return 'This workspace is no longer active. Contact VIDYA AI support.'
  if (lower.includes('credential') || lower.includes('password') || lower.includes('invalid') || lower.includes('incorrect'))
    return 'Incorrect email or password. Please try again.'
  if (lower.includes('locked') || lower.includes('too many'))
    return 'Account temporarily locked. Try again later or reset your password.'
  return raw
}

export default function LoginPage() {
  const navigate = useNavigate()
  const auth = useAuth()

  const [slug,      setSlug]      = useState(localStorage.getItem('vidya_tenant_slug') ?? '')
  const [email,     setEmail]     = useState('')
  const [password,  setPassword]  = useState('')
  const [error,     setError]     = useState('')
  const [loading,   setLoading]   = useState(false)

  const [branding,        setBranding]        = useState<TenantBranding | null>(null)
  const [brandingLoading, setBrandingLoading] = useState(false)
  const [slugError,       setSlugError]       = useState('')

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Fetch tenant branding when slug changes (debounced 600 ms)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const trimmed = slug.trim()
    if (!trimmed) { setBranding(null); setSlugError(''); return }

    debounceRef.current = setTimeout(async () => {
      setBrandingLoading(true)
      setSlugError('')
      try {
        const { data } = await axios.get<TenantBranding>('/api/auth/branding', {
          headers: { 'X-Tenant-Slug': trimmed },
        })
        setBranding(data)
      } catch {
        setBranding(null)
        // Don't surface error yet — user may still be typing
      } finally {
        setBrandingLoading(false)
      }
    }, 600)
  }, [slug])

  const primaryColor = branding?.primary_color  ?? DEFAULT_PRIMARY
  const accentColor  = branding?.secondary_color ?? DEFAULT_ACCENT

  // Colors safe to use on the always-dark left panel (luminance must clear dark bg)
  const safeOnDark = isLight(accentColor) ? accentColor : DEFAULT_ACCENT

  // Colors safe to use on white/light surfaces (must be dark enough to read)
  const safeOnLight = isLight(primaryColor) ? DEFAULT_PRIMARY : primaryColor

  // Button text: white on dark primaryColor, near-black on light primaryColor
  const btnTextColor = isLight(primaryColor) ? '#0f172a' : '#ffffff'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const trimmed = slug.trim()
    if (!trimmed) { setSlugError('Enter your university workspace ID.'); return }
    setError('')
    setSlugError('')
    setLoading(true)
    try {
      await auth.login(trimmed, email.trim(), password)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(classifyError(getErrorMessage(err)))
    } finally {
      setLoading(false)
    }
  }

  const universityName = branding?.name || null

  return (
    <div className="min-h-screen flex bg-[#f4f7ff]">

      {/* ── Left brand panel ─────────────────────────────────────── */}
      {/* Background is always dark — tenant colors appear only as low-opacity accents */}
      <div
        className="hidden lg:flex lg:w-[46%] flex-col px-12 py-12 relative overflow-hidden text-white"
        style={{ background: 'linear-gradient(135deg, #071a34 0%, #0d2347 50%, #06162d 100%)' }}
      >
        {/* Subtle tenant-color tint layer — capped at 12% so dark text is never needed */}
        <div
          className="absolute inset-0"
          style={{ background: `${primaryColor}1e` }}
        />
        {/* Dot grid */}
        <div
          className="absolute inset-0 opacity-[0.05]"
          style={{ backgroundImage: 'radial-gradient(circle, #ffffff 1px, transparent 1px)', backgroundSize: '26px 26px' }}
        />
        {/* Grid lines */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `linear-gradient(${safeOnDark}55 1px, transparent 1px), linear-gradient(90deg, ${safeOnDark}55 1px, transparent 1px)`,
            backgroundSize: '56px 56px',
          }}
        />
        {/* Ambient glows — low opacity so background stays dark regardless of tenant color */}
        <div className="absolute top-0 right-0 w-96 h-96 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2"
          style={{ background: `${primaryColor}1a` }} />
        <div className="absolute top-1/4 right-1/3 w-72 h-72 rounded-full blur-3xl"
          style={{ background: `${safeOnDark}18` }} />
        <div className="absolute bottom-0 left-0 w-72 h-72 rounded-full blur-3xl translate-y-1/3 -translate-x-1/3"
          style={{ background: `${safeOnDark}12` }} />

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
          <div className="mb-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-200">
              <Sparkles className="h-3.5 w-3.5" />
              AI-Powered Academic Intelligence
            </span>
          </div>

          <div className="mb-8">
            <h1 className="flex items-baseline gap-3 text-5xl font-extrabold leading-none tracking-tighter">
              <span className="text-white">VIDYA</span>
              <span className="text-[24px] font-black tracking-[0.16em] uppercase" style={{ color: safeOnDark }}>AI</span>
            </h1>
            <p className="mt-4 text-slate-300 text-[15px] leading-relaxed max-w-xs">
              The intelligent academic management platform built for modern universities and institutions.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div
                key={title}
                className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm hover:bg-white/8 transition-colors"
              >
                <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/15 bg-white/10 mb-3">
                  <Icon className="h-4.5 w-4.5" style={{ color: safeOnDark }} />
                </div>
                <p className="text-sm font-semibold text-white leading-tight mb-1">{title}</p>
                <p className="text-[11px] text-slate-300 leading-snug">{desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Trust strip */}
        <div className="relative z-10 pt-8">
          <div className="flex flex-wrap gap-3 mb-6">
            {TRUST_ITEMS.map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[10px] font-medium text-slate-200">
                <Icon className="h-3 w-3" style={{ color: safeOnDark }} />
                {label}
              </div>
            ))}
          </div>
          <div className="border-t border-white/10 pt-5">
            <p className="text-slate-400 text-xs">© 2026 VIDYA AI Academic Platform. All rights reserved.</p>
            <p className="text-slate-500 text-[10px] mt-0.5 font-medium tracking-wide uppercase">Powered by VIDYA AI</p>
          </div>
        </div>
      </div>

      {/* ── Right login panel ───────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center bg-[#f4f7ff] px-5 py-12">
        <div className="w-full max-w-[22rem]">

          {/* Mobile-only logo */}
          <div className="lg:hidden flex items-center gap-2.5 mb-8 justify-center">
            {branding?.logo_url ? (
              <img src={branding.logo_url} alt={branding.name} className="h-10 w-10 rounded-xl object-contain" />
            ) : (
              <img src="/branding/sherpavector-logo.png" alt="VIDYA AI" className="h-9 w-9 rounded-xl object-contain" />
            )}
            <div>
              <p className="text-sm font-bold text-gray-900 leading-none">{universityName ?? 'VIDYA AI'}</p>
              <p className="text-[10px] text-gray-400 mt-0.5">Academic AI Workspace</p>
            </div>
          </div>

          {/* Tenant branding banner — shown once branding is loaded */}
          {branding && (
            <div className="mb-5 flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm">
              {branding.logo_url ? (
                <img src={branding.logo_url} alt={branding.name} className="h-10 w-10 rounded-lg object-contain flex-shrink-0" />
              ) : (
                <div className="flex h-10 w-10 items-center justify-center rounded-lg flex-shrink-0"
                  style={{ backgroundColor: `${safeOnLight}18` }}>
                  <Building2 className="h-5 w-5" style={{ color: safeOnLight }} />
                </div>
              )}
              <div className="min-w-0">
                <p className="text-sm font-bold text-slate-900 truncate">{branding.name}</p>
                <p className="text-[11px] text-slate-400">Powered by VIDYA AI</p>
              </div>
              <CheckCircle2 className="h-4 w-4 flex-shrink-0 ml-auto" style={{ color: safeOnLight }} />
            </div>
          )}

          {/* Form card */}
          <div className="relative bg-white rounded-[1.75rem] shadow-[0_20px_60px_rgba(2,6,23,0.09)] border border-slate-200/70 p-8 overflow-hidden">
            <div
              className="pointer-events-none absolute inset-0 opacity-40"
              style={{
                background: `radial-gradient(circle at 10% 0%, ${primaryColor}18, transparent 35%), radial-gradient(circle at 90% 20%, ${accentColor}12, transparent 40%)`,
              }}
            />
            <div className="relative">
              <div className="mb-6">
                <h2 className="text-[1.4rem] font-black tracking-tight text-slate-950">Welcome back</h2>
                <p className="text-sm text-slate-500 mt-1">
                  {universityName
                    ? `Sign in to ${universityName}`
                    : "Sign in to your institution's workspace"}
                </p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">

                {/* University Workspace */}
                <div className="space-y-1.5">
                  <label htmlFor="slug" className="block text-sm font-semibold text-slate-700">
                    University Workspace
                  </label>
                  <div className="relative">
                    <Input
                      id="slug"
                      value={slug}
                      onChange={(e) => { setSlug(e.target.value); setSlugError('') }}
                      placeholder="e.g. dsu-university"
                      required
                      className="h-11 rounded-xl border-slate-200 bg-white/90 px-4 pr-9 focus-visible:ring-2 focus-visible:ring-offset-0"
                      style={{ '--tw-ring-color': accentColor } as React.CSSProperties}
                    />
                    {brandingLoading && (
                      <div className="absolute right-3 top-1/2 -translate-y-1/2">
                        <div className="h-4 w-4 rounded-full border-2 border-slate-200 border-t-transparent animate-spin"
                          style={{ borderTopColor: safeOnLight }} />
                      </div>
                    )}
                  </div>
                  {slugError ? (
                    <p className="text-xs text-red-600 flex items-center gap-1">
                      <AlertCircle className="h-3 w-3 flex-shrink-0" />{slugError}
                    </p>
                  ) : (
                    <p className="text-xs text-slate-400">Enter your university workspace ID</p>
                  )}
                </div>

                {/* Email */}
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
                    className="h-11 rounded-xl border-slate-200 bg-white/90 px-4 focus-visible:ring-2 focus-visible:ring-offset-0"
                    style={{ '--tw-ring-color': accentColor } as React.CSSProperties}
                  />
                </div>

                {/* Password */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3">
                    <label htmlFor="password" className="block text-sm font-semibold text-slate-700">
                      Password
                    </label>
                    <Link
                      to="/forgot-password"
                      className="text-xs font-semibold hover:underline"
                      style={{ color: safeOnLight }}
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
                    className="h-11 rounded-xl border-slate-200 bg-white/90 px-4 focus-visible:ring-2 focus-visible:ring-offset-0"
                    style={{ '--tw-ring-color': accentColor } as React.CSSProperties}
                  />
                </div>

                {/* Error */}
                {error && (
                  <div className="flex items-start gap-2 text-sm text-red-700 rounded-xl bg-red-50 px-3.5 py-2.5 border border-red-100">
                    <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                    <span>{error}</span>
                  </div>
                )}

                {/* Submit */}
                <Button
                  type="submit"
                  className="w-full h-11 rounded-2xl font-semibold transition-all"
                  style={{ backgroundColor: primaryColor, color: btnTextColor, boxShadow: `0 10px 35px ${primaryColor}33` }}
                  disabled={loading}
                >
                  {loading ? 'Signing in…' : 'Sign in'}
                </Button>
              </form>

              {/* Secure access note */}
              <div className="mt-5 rounded-xl border bg-slate-50/80 p-3.5"
                style={{ borderColor: `${accentColor}30` }}>
                <div className="flex items-start gap-2.5">
                  <Lock className="h-4 w-4 mt-0.5 flex-shrink-0" style={{ color: safeOnLight }} />
                  <p className="text-xs text-slate-600 leading-relaxed">
                    <span className="font-semibold text-slate-800">Secure access</span> — all sign-ins are encrypted and audit-monitored.
                  </p>
                </div>
              </div>

              {/* Help text */}
              <div className="mt-4 pt-4 border-t border-slate-200/70">
                <p className="text-xs text-center text-slate-500">
                  Don't know your workspace ID?{' '}
                  <span className="text-slate-700 font-semibold">Contact your university administrator.</span>
                </p>
              </div>
            </div>
          </div>

          {/* Trust strip — mobile */}
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {TRUST_ITEMS.map(({ icon: Icon, label }) => (
              <div key={label} className="flex items-center gap-1 rounded-full border border-slate-200 bg-white/70 px-2.5 py-1 text-[10px] font-medium text-slate-500">
                <Icon className="h-3 w-3 text-slate-400" />
                {label}
              </div>
            ))}
          </div>

          <p className="text-[11px] text-center text-gray-400 mt-4">
            Powered by VIDYA AI
          </p>
        </div>
      </div>

    </div>
  )
}
