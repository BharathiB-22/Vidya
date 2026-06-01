import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight, Bot, Building2, Globe, HardDrive, Palette,
  RefreshCw, Shield, Zap,
} from 'lucide-react'
import { getPlatformSettings } from '@/lib/api/platform'
import type { PlatformSettings } from '@/lib/api/platform'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ENV_BADGE: Record<string, { label: string; color: string; bg: string; border: string }> = {
  production:  { label: 'Production',  color: '#34d399', bg: 'rgba(16,185,129,0.12)',  border: 'rgba(16,185,129,0.3)'  },
  staging:     { label: 'Staging',     color: '#60a5fa', bg: 'rgba(96,165,250,0.12)',  border: 'rgba(96,165,250,0.3)'  },
  development: { label: 'Development', color: '#fbbf24', bg: 'rgba(251,191,36,0.12)',  border: 'rgba(251,191,36,0.3)'  },
}

function envBadge(env: string) {
  return ENV_BADGE[env] ?? { label: env, color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)' }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionCard({
  icon: Icon, title, iconColor, children,
}: {
  icon: typeof Globe; title: string; iconColor: string; children: React.ReactNode
}) {
  return (
    <div
      className="rounded-xl p-5"
      style={{
        background: 'linear-gradient(180deg, rgba(14,24,45,0.95) 0%, rgba(10,18,35,0.95) 100%)',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: iconColor + '18', border: `1px solid ${iconColor}30` }}
        >
          <Icon className="h-4.5 w-4.5" style={{ color: iconColor, width: 18, height: 18 }} />
        </div>
        <h2 className="text-base font-bold text-white">{title}</h2>
      </div>
      <div className="space-y-3">{children}</div>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2" style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
      <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide whitespace-nowrap">{label}</span>
      <div className="flex items-center gap-2 min-w-0 justify-end">{children}</div>
    </div>
  )
}

function Val({ children }: { children: React.ReactNode }) {
  return <span className="text-sm font-semibold text-slate-200 truncate text-right">{children}</span>
}

function Mono({ children }: { children: React.ReactNode }) {
  return <span className="text-xs font-mono text-slate-400 truncate text-right">{children}</span>
}

function Badge({
  label, color, bg, border,
}: { label: string; color: string; bg: string; border: string }) {
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide whitespace-nowrap"
      style={{ color, background: bg, border: `1px solid ${border}` }}
    >
      {label}
    </span>
  )
}

function EnabledBadge({ enabled, trueLabel = 'Enabled', falseLabel = 'Disabled' }: {
  enabled: boolean; trueLabel?: string; falseLabel?: string
}) {
  return enabled ? (
    <Badge label={trueLabel} color="#34d399" bg="rgba(16,185,129,0.12)" border="rgba(16,185,129,0.3)" />
  ) : (
    <Badge label={falseLabel} color="#f87171" bg="rgba(239,68,68,0.1)" border="rgba(239,68,68,0.25)" />
  )
}

function ActionButton({
  icon: Icon, label, sub, onClick, color,
}: { icon: typeof Zap; label: string; sub: string; onClick?: () => void; color: string }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all"
      style={{ background: color + '0c', border: `1px solid ${color}20` }}
      onMouseEnter={(e) => { e.currentTarget.style.background = color + '18'; e.currentTarget.style.borderColor = color + '40' }}
      onMouseLeave={(e) => { e.currentTarget.style.background = color + '0c'; e.currentTarget.style.borderColor = color + '20' }}
    >
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: color + '18', border: `1px solid ${color}30` }}
      >
        <Icon className="h-4 w-4" style={{ color }} />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-slate-200">{label}</p>
        <p className="text-[11px] text-slate-600">{sub}</p>
      </div>
      <ArrowRight className="h-4 w-4 flex-shrink-0" style={{ color }} />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const navigate = useNavigate()
  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ['platform-settings'],
    queryFn: getPlatformSettings,
    staleTime: 60_000,
  })

  const s = data as PlatformSettings | undefined
  const env = envBadge(s?.environment ?? 'development')

  return (
    <main className="max-w-screen-xl mx-auto px-8 py-8">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Settings</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Read-only view of the current platform configuration — no secrets are displayed
          </p>
        </div>
        <div className="flex items-center gap-3">
          {dataUpdatedAt > 0 && (
            <span className="text-xs text-slate-600">
              Last loaded {new Date(dataUpdatedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold text-slate-300 transition-all disabled:opacity-50"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24 text-slate-600">
          <RefreshCw className="h-5 w-5 animate-spin mr-2" />
          Loading configuration…
        </div>
      )}

      {/* Error */}
      {isError && !isLoading && (
        <div
          className="rounded-xl px-6 py-5 mb-6 flex items-center gap-3"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
        >
          <Shield className="h-5 w-5 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-300">Failed to load platform settings</p>
            <p className="text-xs text-slate-500 mt-0.5">Check that the backend is running.</p>
          </div>
          <button
            onClick={() => refetch()}
            className="ml-auto text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-lg"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            Retry
          </button>
        </div>
      )}

      {s && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ── 1. Platform Profile ────────────────────────────────────── */}
          <SectionCard icon={Globe} title="Platform Profile" iconColor="#6366f1">
            <Row label="Platform Name">
              <Val>{s.platform_name}</Val>
              <Badge label="Live" color="#34d399" bg="rgba(16,185,129,0.12)" border="rgba(16,185,129,0.3)" />
            </Row>
            <Row label="Company">
              <Val>{s.company_name}</Val>
            </Row>
            <Row label="Support Email">
              <Mono>{s.support_email}</Mono>
            </Row>
            <Row label="Environment">
              <Badge label={env.label} color={env.color} bg={env.bg} border={env.border} />
            </Row>
            <Row label="Build Version">
              <Val>{s.build_version}</Val>
            </Row>
          </SectionCard>

          {/* ── 2. Branding ───────────────────────────────────────────── */}
          <SectionCard icon={Palette} title="Platform Branding" iconColor="#a78bfa">
            <Row label="Logo">
              <div className="flex items-center gap-2">
                <img
                  src="/branding/sherpavector-logo.png"
                  alt="SherpaVector"
                  className="h-7 w-7 rounded-lg object-contain"
                  style={{ filter: 'drop-shadow(0 0 6px rgba(16,185,129,0.3))' }}
                />
                <Val>SherpaVector</Val>
              </div>
            </Row>
            <Row label="Primary Color">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full border border-white/10" style={{ background: '#10b981' }} />
                <Mono>#10b981</Mono>
              </div>
            </Row>
            <Row label="Accent Color">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded-full border border-white/10" style={{ background: '#6366f1' }} />
                <Mono>#6366f1</Mono>
              </div>
            </Row>
            <div
              className="mt-3 rounded-lg px-3 py-2.5 text-[11px] text-slate-500 leading-relaxed"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              Each university can configure its own logo and brand colours from their{' '}
              <span className="text-slate-400 font-semibold">Institution Settings</span> panel.
            </div>
          </SectionCard>

          {/* ── 3. AI Configuration ───────────────────────────────────── */}
          <SectionCard icon={Bot} title="AI Configuration" iconColor="#f59e0b">
            <Row label="Active Provider">
              <Badge
                label={s.ai_provider.toUpperCase()}
                color="#f59e0b"
                bg="rgba(245,158,11,0.12)"
                border="rgba(245,158,11,0.3)"
              />
            </Row>
            <Row label="Gemini">
              <div className="flex items-center gap-2">
                <Mono>{s.gemini_model}</Mono>
                <EnabledBadge enabled={s.gemini_configured} trueLabel="Configured" falseLabel="Not set" />
              </div>
            </Row>
            <Row label="Groq">
              <div className="flex items-center gap-2">
                <Mono>{s.groq_model}</Mono>
                <EnabledBadge enabled={s.groq_configured} trueLabel="Configured" falseLabel="Not set" />
              </div>
            </Row>
            <div
              className="mt-3 rounded-lg px-3 py-2.5 text-[11px] text-slate-500"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}
            >
              API keys are stored securely in environment variables and are never displayed.
            </div>
          </SectionCard>

          {/* ── 4. Storage ────────────────────────────────────────────── */}
          <SectionCard icon={HardDrive} title="Storage" iconColor="#06b6d4">
            <Row label="Provider">
              <Val>{s.storage_provider}</Val>
            </Row>
            <Row label="Endpoint">
              <Mono>{s.s3_endpoint}</Mono>
            </Row>
            <Row label="Bucket">
              <Mono>{s.s3_bucket}</Mono>
            </Row>
            <Row label="Region">
              <Mono>{s.s3_region}</Mono>
            </Row>
            <Row label="TLS / SSL">
              <EnabledBadge enabled={s.s3_use_ssl} trueLabel="Enabled" falseLabel="Disabled" />
            </Row>
            <Row label="Max Upload">
              <Val>{s.max_upload_mb} MB</Val>
            </Row>
          </SectionCard>

          {/* ── 5. Security ───────────────────────────────────────────── */}
          <SectionCard icon={Shield} title="Security" iconColor="#10b981">
            <Row label="JWT Authentication">
              <EnabledBadge enabled={s.jwt_enabled} />
            </Row>
            <Row label="Role-Based Access Control">
              <EnabledBadge enabled={s.rbac_enabled} />
            </Row>
            <Row label="Multi-Tenant Isolation">
              <EnabledBadge enabled={s.tenant_isolation} />
            </Row>
            <Row label="Audit Logging">
              <EnabledBadge enabled={s.audit_logging_enabled} />
            </Row>
            <Row label="Soft Delete Protection">
              <EnabledBadge enabled={s.soft_delete_enabled} />
            </Row>
            <Row label="Access Token Expiry">
              <Val>{s.access_token_expire_minutes} min</Val>
            </Row>
            <Row label="Refresh Token Expiry">
              <Val>{s.refresh_token_expire_days} days</Val>
            </Row>
            <Row label="Email Notifications">
              <div className="flex items-center gap-2">
                <Mono>{s.smtp_from}</Mono>
                <EnabledBadge enabled={s.email_enabled} />
              </div>
            </Row>
          </SectionCard>

          {/* ── 6. System Actions ─────────────────────────────────────── */}
          <SectionCard icon={Zap} title="System Actions" iconColor="#34d399">
            <ActionButton
              icon={RefreshCw}
              label="Refresh Configuration"
              sub="Reload settings from the backend"
              color="#6366f1"
              onClick={() => refetch()}
            />
            <ActionButton
              icon={Building2}
              label="Platform Monitoring"
              sub="Service health, jobs, AI providers, recent events"
              color="#10b981"
              onClick={() => navigate('/admin/monitoring')}
            />
            <ActionButton
              icon={Shield}
              label="Audit Logs"
              sub="Full event history across all tenants"
              color="#60a5fa"
              onClick={() => navigate('/admin/audit-logs')}
            />
          </SectionCard>

        </div>
      )}
    </main>
  )
}
