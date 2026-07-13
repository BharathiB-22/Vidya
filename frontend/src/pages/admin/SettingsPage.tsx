import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight, Bot, Building2, Globe, HardDrive, Palette,
  RefreshCw, Shield, Zap,
} from 'lucide-react'
import { getPlatformSettings } from '@/lib/api/platform'
import type { PlatformSettings } from '@/lib/api/platform'
import { tint } from '@/lib/platformPalette'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ENV_BADGE: Record<string, { label: string; color: string; bg: string; border: string }> = {
  production:  { label: 'Production',  color: 'var(--pc-emerald-400)', bg: 'var(--pc-t-emerald-12)',  border: 'var(--pc-t-emerald-30)'  },
  staging:     { label: 'Staging',     color: 'var(--pc-blue-400)', bg: 'var(--pc-t-bluelt-12)',  border: 'var(--pc-t-bluelt-30)'  },
  development: { label: 'Development', color: 'var(--pc-amber-400)', bg: 'var(--pc-t-amberlt-12)',  border: 'var(--pc-t-amberlt-30)'  },
}

function envBadge(env: string) {
  return ENV_BADGE[env] ?? { label: env, color: 'var(--pc-slate-400)', bg: 'var(--pc-t-slatelt-10)', border: 'var(--pc-t-slatelt-20)' }
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
        background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
        border: '1px solid var(--pc-t-overlay-08)',
      }}
    >
      <div className="flex items-center gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: tint(iconColor, 9.41), border: `1px solid ${tint(iconColor, 18.82)}` }}
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
    <div className="flex items-center justify-between gap-3 py-2" style={{ borderBottom: '1px solid var(--pc-t-overlay-04)' }}>
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
    <Badge label={trueLabel} color="var(--pc-emerald-400)" bg="var(--pc-t-emerald-12)" border="var(--pc-t-emerald-30)" />
  ) : (
    <Badge label={falseLabel} color="var(--pc-red-400)" bg="var(--pc-t-red-10)" border="var(--pc-t-red-25)" />
  )
}

function ActionButton({
  icon: Icon, label, sub, onClick, color,
}: { icon: typeof Zap; label: string; sub: string; onClick?: () => void; color: string }) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all"
      style={{ background: tint(color, 4.71), border: `1px solid ${tint(color, 12.55)}` }}
      onMouseEnter={(e) => { e.currentTarget.style.background = tint(color, 9.41); e.currentTarget.style.borderColor = tint(color, 25.1) }}
      onMouseLeave={(e) => { e.currentTarget.style.background = tint(color, 4.71); e.currentTarget.style.borderColor = tint(color, 12.55) }}
    >
      <div
        className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: tint(color, 9.41), border: `1px solid ${tint(color, 18.82)}` }}
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
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
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
          style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
        >
          <Shield className="h-5 w-5 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-300">Failed to load platform settings</p>
            <p className="text-xs text-slate-500 mt-0.5">Check that the backend is running.</p>
          </div>
          <button
            onClick={() => refetch()}
            className="ml-auto text-xs text-slate-400 hover:text-slate-200 px-3 py-1.5 rounded-lg"
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
          >
            Retry
          </button>
        </div>
      )}

      {s && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* ── 1. Platform Profile ────────────────────────────────────── */}
          <SectionCard icon={Globe} title="Platform Profile" iconColor="var(--pc-indigo-500)">
            <Row label="Platform Name">
              <Val>{s.platform_name}</Val>
              <Badge label="Live" color="var(--pc-emerald-400)" bg="var(--pc-t-emerald-12)" border="var(--pc-t-emerald-30)" />
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
          <SectionCard icon={Palette} title="Platform Branding" iconColor="var(--pc-violet-400)">
            <Row label="Logo">
              <div className="flex items-center gap-2">
                <img
                  src="/branding/sherpavector-logo.png"
                  alt="SherpaVector"
                  className="h-7 w-7 rounded-lg object-contain"
                  style={{ filter: 'drop-shadow(0 0 6px var(--pc-t-emerald-30))' }}
                />
                <Val>SherpaVector</Val>
              </div>
            </Row>
            {/* These swatches report the platform's brand colours, which do not
                change with the console theme — they must keep matching the hex
                printed beside them. */}
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
              style={{ background: 'var(--pc-t-overlay-03)', border: '1px solid var(--pc-t-overlay-06)' }}
            >
              Each university can configure its own logo and brand colours from their{' '}
              <span className="text-slate-400 font-semibold">Institution Settings</span> panel.
            </div>
          </SectionCard>

          {/* ── 3. AI Providers ───────────────────────────────────────── */}
          <SectionCard icon={Bot} title="AI Providers" iconColor="var(--pc-amber-500)">
            <Row label="Strategy">
              <Badge
                label={s.ai_provider.toUpperCase()}
                color="var(--pc-amber-500)"
                bg="var(--pc-t-amber-12)"
                border="var(--pc-t-amber-30)"
              />
            </Row>
            <Row label="Gemini">
              <div className="flex items-center gap-2">
                <Mono>{s.gemini_model}</Mono>
                <EnabledBadge enabled={s.gemini_enabled} />
                <EnabledBadge enabled={s.gemini_configured} trueLabel="Key set" falseLabel="No key" />
              </div>
            </Row>
            <Row label="Groq">
              <div className="flex items-center gap-2">
                <Mono>{s.groq_model}</Mono>
                <EnabledBadge enabled={s.groq_enabled} />
                <EnabledBadge enabled={s.groq_configured} trueLabel="Key set" falseLabel="No key" />
              </div>
            </Row>
            <Row label="DeepSeek">
              <div className="flex items-center gap-2">
                <Mono>{s.deepseek_model}</Mono>
                <EnabledBadge enabled={s.deepseek_enabled} />
                <EnabledBadge enabled={s.deepseek_configured} trueLabel="Key set" falseLabel="No key" />
              </div>
            </Row>
            <div
              className="mt-3 rounded-lg px-3 py-2.5 text-[11px] text-slate-500 leading-relaxed"
              style={{ background: 'var(--pc-t-overlay-03)', border: '1px solid var(--pc-t-overlay-06)' }}
            >
              Fallback order: <span className="text-slate-400 font-semibold">Gemini → Groq → DeepSeek</span>.
              Disable a provider via <span className="font-mono">AI_*_ENABLED=false</span> in the environment.
              API keys are never displayed.
            </div>
          </SectionCard>

          {/* ── 4. Storage ────────────────────────────────────────────── */}
          <SectionCard icon={HardDrive} title="Storage" iconColor="var(--pc-cyan-500)">
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
          <SectionCard icon={Shield} title="Security" iconColor="var(--pc-emerald-500)">
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
          <SectionCard icon={Zap} title="System Actions" iconColor="var(--pc-emerald-400)">
            <ActionButton
              icon={RefreshCw}
              label="Refresh Configuration"
              sub="Reload settings from the backend"
              color="var(--pc-indigo-500)"
              onClick={() => refetch()}
            />
            <ActionButton
              icon={Building2}
              label="Platform Monitoring"
              sub="Service health, jobs, AI providers, recent events"
              color="var(--pc-emerald-500)"
              onClick={() => navigate('/admin/monitoring')}
            />
            <ActionButton
              icon={Shield}
              label="Audit Logs"
              sub="Full event history across all tenants"
              color="var(--pc-blue-400)"
              onClick={() => navigate('/admin/audit-logs')}
            />
          </SectionCard>

        </div>
      )}
    </main>
  )
}
