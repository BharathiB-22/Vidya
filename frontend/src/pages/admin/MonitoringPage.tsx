import { useQuery } from '@tanstack/react-query'
import {
  Activity, AlertTriangle, Archive, Bot, Brain,
  CheckCircle2, Circle, Clock, Database, Cpu, HardDrive,
  RefreshCw, ScrollText, Server, Wifi, Zap, Building2,
} from 'lucide-react'
import { getPlatformStats } from '@/lib/api/platform'
import type { ServiceHealthItem, AuditEventSummary } from '@/lib/api/platform'
import { tint } from '@/lib/platformPalette'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function fmtLatency(ms: number): string {
  if (ms < 1) return '<1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function eventLabel(type: string): string {
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

const EVENT_COLORS: Record<string, string> = {
  TENANT_PROVISIONED:  'var(--pc-emerald-400)',
  TENANT_UPDATED:      'var(--pc-blue-400)',
  TENANT_DEACTIVATED:  'var(--pc-amber-400)',
  TENANT_ARCHIVED:     'var(--pc-stone-400)',
  TENANT_REACTIVATED:  'var(--pc-emerald-400)',
  TENANT_DELETED:      'var(--pc-red-400)',
  PLATFORM_LOGIN_SUCCESS: 'var(--pc-indigo-400)',
  PLATFORM_LOGIN_FAILURE: 'var(--pc-red-400)',
}

const SERVICE_ICONS: Record<string, typeof Database> = {
  db:     Database,
  redis:  Zap,
  s3:     HardDrive,
  qdrant: Brain,
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeader({ icon: Icon, title, sub }: { icon: typeof Database; title: string; sub?: string }) {
  return (
    <div className="flex items-center gap-3 mb-4">
      <div
        className="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: 'var(--pc-t-emerald-10)', border: '1px solid var(--pc-t-emerald-20)' }}
      >
        <Icon className="h-4.5 w-4.5 text-emerald-400" style={{ width: 18, height: 18 }} />
      </div>
      <div>
        <h2 className="text-lg font-bold text-white leading-tight">{title}</h2>
        {sub && <p className="text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  )
}

function HealthCard({ item }: { item: ServiceHealthItem }) {
  const Icon = SERVICE_ICONS[item.service] ?? Server
  const healthy  = item.status === 'healthy'
  const skipped  = item.status === 'skipped'
  const unhealthy = item.status === 'unhealthy'

  const statusColor  = healthy ? 'var(--pc-emerald-400)' : skipped ? 'var(--pc-slate-400)' : 'var(--pc-red-400)'
  const statusBg     = healthy ? 'var(--pc-t-emerald-08)' : skipped ? 'var(--pc-t-slate-08)' : 'var(--pc-t-red-08)'
  const statusBorder = healthy ? 'var(--pc-t-emerald-20)'  : skipped ? 'var(--pc-t-slate-15)' : 'var(--pc-t-red-30)'
  const iconBg       = healthy ? 'var(--pc-t-emerald-12)' : skipped ? 'var(--pc-t-slate-10)'  : 'var(--pc-t-red-12)'
  const iconBorder   = healthy ? 'var(--pc-t-emerald-25)' : skipped ? 'var(--pc-t-slate-20)'  : 'var(--pc-t-red-30)'

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: statusBg, border: `1px solid ${statusBorder}` }}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: iconBg, border: `1px solid ${iconBorder}` }}
        >
          <Icon className="h-5 w-5" style={{ color: statusColor }} />
        </div>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
          style={{ background: iconBg, color: statusColor, border: `1px solid ${iconBorder}` }}
        >
          {item.status}
        </span>
      </div>
      <p className="text-base font-bold text-white mb-0.5">{item.label}</p>
      <p className="text-[11px] text-slate-500">{item.service}</p>
      {!skipped && (
        <p className="text-xs text-slate-400 mt-2">
          Latency: <span style={{ color: statusColor }}>{fmtLatency(item.latency_ms)}</span>
        </p>
      )}
      {unhealthy && item.error_msg && (
        <p className="text-[11px] text-red-400 mt-1 truncate" title={item.error_msg}>
          {item.error_msg}
        </p>
      )}
      {skipped && (
        <p className="text-[11px] text-slate-600 mt-1">Not configured</p>
      )}
    </div>
  )
}

function KpiCard({
  label, value, sub, icon: Icon, color,
}: {
  label: string; value: string | number; sub?: string; icon: typeof Database; color: string
}) {
  return (
    <div
      className="rounded-xl p-4 flex items-center gap-4"
      style={{
        background: 'linear-gradient(135deg, var(--pc-t-surf3-90), var(--pc-t-surf4-90))',
        border: '1px solid var(--pc-t-overlay-07)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
      }}
    >
      <div
        className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: tint(color, 9.41), border: `1px solid ${tint(color, 18.82)}` }}
      >
        <Icon className="h-5 w-5" style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-white leading-tight">{value}</p>
        <p className="text-xs font-semibold text-slate-400 mt-0.5 truncate">{label}</p>
        {sub && <p className="text-[11px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function JobBar({
  label, value, total, color,
}: {
  label: string; value: number; total: number; color: string
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-semibold text-slate-300">{label}</span>
        <span className="text-sm font-bold" style={{ color }}>{value.toLocaleString()}</span>
      </div>
      <div className="h-1.5 rounded-full" style={{ background: 'var(--pc-t-overlay-06)' }}>
        <div
          className="h-1.5 rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  )
}

function AICard({ name, configured, model, active }: {
  name: string; configured: boolean; model: string; active: boolean
}) {
  const statusColor  = configured ? 'var(--pc-emerald-400)' : 'var(--pc-red-400)'
  const statusBg     = configured ? 'var(--pc-t-emerald-08)' : 'var(--pc-t-red-06)'
  const statusBorder = configured ? 'var(--pc-t-emerald-20)' : 'var(--pc-t-red-20)'

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: statusBg, border: `1px solid ${statusBorder}` }}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: tint(statusColor, 9.41), border: `1px solid ${tint(statusColor, 18.82)}` }}
        >
          <Bot className="h-5 w-5" style={{ color: statusColor }} />
        </div>
        <div className="flex flex-col items-end gap-1">
          {active && (
            <span
              className="text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-widest"
              style={{ background: 'var(--pc-t-emerald-15)', color: 'var(--pc-emerald-400)', border: '1px solid var(--pc-t-emerald-30)' }}
            >
              Active
            </span>
          )}
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
            style={{ background: tint(statusColor, 9.41), color: statusColor, border: `1px solid ${tint(statusColor, 18.82)}` }}
          >
            {configured ? 'Ready' : 'Not configured'}
          </span>
        </div>
      </div>
      <p className="text-base font-bold text-white mb-0.5">{name}</p>
      <p className="text-[11px] text-slate-500 font-mono truncate">{model}</p>
    </div>
  )
}

function EventRow({ event }: { event: AuditEventSummary }) {
  const color = EVENT_COLORS[event.event_type] ?? 'var(--pc-slate-400)'
  const isSuccess = event.event_type.endsWith('_SUCCESS') || event.event_type === 'TENANT_PROVISIONED' || event.event_type === 'TENANT_REACTIVATED'
  const isError = event.event_type.endsWith('_FAILURE') || event.event_type.endsWith('_FAILED') || event.event_type === 'TENANT_DELETED'

  return (
    <div
      className="flex items-center gap-3 py-2.5"
      style={{ borderBottom: '1px solid var(--pc-t-overlay-04)' }}
    >
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
        style={{ background: tint(color, 9.41), border: `1px solid ${tint(color, 14.51)}` }}
      >
        {isError ? (
          <AlertTriangle className="h-3.5 w-3.5" style={{ color }} />
        ) : isSuccess ? (
          <CheckCircle2 className="h-3.5 w-3.5" style={{ color }} />
        ) : (
          <Circle className="h-3.5 w-3.5" style={{ color }} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-slate-200 truncate">{eventLabel(event.event_type)}</p>
        {event.schema_name && (
          <p className="text-[11px] text-slate-500 font-mono">{event.schema_name}</p>
        )}
      </div>
      <p className="text-[11px] text-slate-600 flex-shrink-0">{timeAgo(event.created_at)}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function MonitoringPage() {
  const { data, isLoading, isError, dataUpdatedAt, refetch, isFetching } = useQuery({
    queryKey: ['platform-stats'],
    queryFn: getPlatformStats,
    refetchInterval: 30_000,
    staleTime: 25_000,
  })

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null

  const jobTotal = data
    ? data.jobs.pending + data.jobs.running + data.jobs.completed + data.jobs.failed
    : 0

  return (
    <main className="max-w-screen-xl mx-auto px-8 py-8">

      {/* Page header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Monitoring</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            {isLoading ? 'Loading…' : data?.all_healthy ? 'All systems operational' : 'Degraded — check service health'}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-slate-600 flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" />
              Updated {lastUpdated}
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

      {/* Loading skeleton */}
      {isLoading && (
        <div className="flex items-center justify-center py-24 text-slate-500">
          <RefreshCw className="h-5 w-5 animate-spin mr-2" />
          Loading platform stats…
        </div>
      )}

      {/* Error state */}
      {isError && !isLoading && (
        <div
          className="rounded-xl px-6 py-5 mb-6 flex items-center gap-3"
          style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
        >
          <AlertTriangle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <div>
            <p className="text-sm font-semibold text-red-300">Failed to load monitoring data</p>
            <p className="text-xs text-slate-500 mt-0.5">Check that the backend is running. Auto-retrying every 30s.</p>
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

      {data && (
        <div className="space-y-8">

          {/* ── 1. Platform Health ─────────────────────────────────────── */}
          <section>
            <SectionHeader
              icon={Activity}
              title="Platform Health"
              sub="Real-time service connectivity checks"
            />
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              {data.health.map((item) => (
                <HealthCard key={item.service} item={item} />
              ))}
              {/* API server itself is always reachable if this page loads */}
              <div
                className="rounded-xl p-4"
                style={{ background: 'var(--pc-t-emerald-08)', border: '1px solid var(--pc-t-emerald-20)' }}
              >
                <div className="flex items-start justify-between gap-2 mb-3">
                  <div
                    className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: 'var(--pc-t-emerald-12)', border: '1px solid var(--pc-t-emerald-25)' }}
                  >
                    <Wifi className="h-5 w-5 text-emerald-400" />
                  </div>
                  <span
                    className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
                    style={{ background: 'var(--pc-t-emerald-12)', color: 'var(--pc-emerald-400)', border: '1px solid var(--pc-t-emerald-25)' }}
                  >
                    healthy
                  </span>
                </div>
                <p className="text-base font-bold text-white mb-0.5">API Server</p>
                <p className="text-[11px] text-slate-500">api</p>
                <p className="text-xs text-slate-400 mt-2">
                  Latency: <span className="text-emerald-400">local</span>
                </p>
              </div>
            </div>
          </section>

          {/* ── 2. Tenant Statistics ──────────────────────────────────── */}
          <section>
            <SectionHeader
              icon={Building2}
              title="Tenant Statistics"
              sub="Live tenant registry counts (excludes deleted)"
            />
            <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
              <KpiCard label="Total"        value={data.tenants.total}        icon={Building2}    color="var(--pc-indigo-500)" />
              <KpiCard label="Active"        value={data.tenants.active}       icon={CheckCircle2} color="var(--pc-emerald-500)" />
              <KpiCard label="Inactive"      value={data.tenants.inactive}     icon={Circle}       color="var(--pc-slate-400)" />
              <KpiCard label="Archived"      value={data.tenants.archived}     icon={Archive}      color="var(--pc-stone-500)" />
              <KpiCard label="Provisioning"  value={data.tenants.provisioning} icon={RefreshCw}    color="var(--pc-amber-400)" />
              <KpiCard label="Failed"        value={data.tenants.failed}       icon={AlertTriangle} color="var(--pc-red-500)" />
            </div>
          </section>

          {/* ── 3 + 4. Jobs + AI Services (side by side) ─────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

            {/* Background Jobs */}
            <section>
              <SectionHeader
                icon={Cpu}
                title="Background Jobs"
                sub={`${data.jobs.total_24h.toLocaleString()} tasks submitted in last 24h`}
              />
              <div
                className="rounded-xl p-5 space-y-4"
                style={{
                  background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
                  border: '1px solid var(--pc-t-overlay-08)',
                }}
              >
                <JobBar label="Completed"  value={data.jobs.completed} total={jobTotal} color="var(--pc-emerald-400)" />
                <JobBar label="Pending"    value={data.jobs.pending}   total={jobTotal} color="var(--pc-amber-400)" />
                <JobBar label="Running"    value={data.jobs.running}   total={jobTotal} color="var(--pc-blue-400)" />
                <JobBar label="Failed"     value={data.jobs.failed}    total={jobTotal} color="var(--pc-red-400)" />
                <div
                  className="pt-3 flex items-center justify-between"
                  style={{ borderTop: '1px solid var(--pc-t-overlay-05)' }}
                >
                  <span className="text-xs text-slate-500">All-time total</span>
                  <span className="text-xl font-bold text-white">{jobTotal.toLocaleString()}</span>
                </div>
              </div>
            </section>

            {/* AI Services */}
            <section>
              <SectionHeader
                icon={Bot}
                title="AI Services"
                sub="Provider configuration and active model"
              />
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {data.ai_services.map((svc) => (
                  <AICard key={svc.name} {...svc} />
                ))}
                {/* Placeholder for future providers */}
                <div
                  className="rounded-xl p-4 flex flex-col items-center justify-center gap-2 col-span-full sm:col-span-1 lg:col-span-2"
                  style={{ background: 'var(--pc-t-overlay-02)', border: '1px dashed var(--pc-t-overlay-08)', minHeight: 80 }}
                >
                  <Zap className="h-4 w-4 text-slate-700" />
                  <p className="text-xs text-slate-700">More providers coming soon</p>
                </div>
              </div>
            </section>
          </div>

          {/* ── 5. Recent Activity ───────────────────────────────────── */}
          <section>
            <SectionHeader
              icon={ScrollText}
              title="Recent System Activity"
              sub="Latest platform-level events across all tenants"
            />
            <div
              className="rounded-xl"
              style={{
                background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
                border: '1px solid var(--pc-t-overlay-08)',
              }}
            >
              {data.recent_events.length === 0 ? (
                <div className="flex items-center justify-center py-10 text-slate-600">
                  <p className="text-sm">No platform events recorded yet.</p>
                </div>
              ) : (
                <div className="px-5 divide-y-0">
                  {data.recent_events.map((event, i) => (
                    <EventRow key={i} event={event} />
                  ))}
                </div>
              )}
            </div>
          </section>

        </div>
      )}
    </main>
  )
}

