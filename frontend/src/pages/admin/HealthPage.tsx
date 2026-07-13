import { useQuery } from '@tanstack/react-query'
import {
  Activity, AlertTriangle, Bot, CheckCircle2, Clock,
  Cpu, Database, HardDrive, RefreshCw, Server,
  ShieldCheck, Wifi, Zap,
} from 'lucide-react'
import { getPlatformHealth } from '@/lib/api/platform'
import type { PlatformDiagnosticService, AIProviderDiagnostic, QueueDiagnostics } from '@/lib/api/platform'
import { tint } from '@/lib/platformPalette'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ServiceStatus = 'healthy' | 'unhealthy' | 'warning' | 'skipped'

const STATUS_STYLE: Record<ServiceStatus, { color: string; bg: string; border: string; label: string }> = {
  healthy:  { color: 'var(--pc-emerald-400)', bg: 'var(--pc-t-emerald-08)',  border: 'var(--pc-t-emerald-20)',  label: 'HEALTHY'  },
  unhealthy:{ color: 'var(--pc-red-400)', bg: 'var(--pc-t-red-08)',   border: 'var(--pc-t-red-25)',   label: 'FAILED'   },
  warning:  { color: 'var(--pc-amber-400)', bg: 'var(--pc-t-amberlt-08)',  border: 'var(--pc-t-amberlt-20)',   label: 'WARNING'  },
  skipped:  { color: 'var(--pc-slate-400)', bg: 'var(--pc-t-slatelt-06)', border: 'var(--pc-t-slatelt-15)', label: 'SKIPPED'  },
}

const SERVICE_ICONS: Record<string, typeof Database> = {
  db:           Database,
  redis:        Zap,
  s3:           HardDrive,
  qdrant:       Activity,
  api:          Wifi,
  celery:       Cpu,
  'celery-heavy': Server,
}

function fmtLatency(ms: number): string {
  if (ms < 1)    return '< 1ms'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function latencyColor(ms: number): string {
  if (ms < 50)   return 'var(--pc-emerald-400)'
  if (ms < 200)  return 'var(--pc-blue-400)'
  if (ms < 500)  return 'var(--pc-amber-400)'
  return 'var(--pc-red-400)'
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
        <Icon className="h-[18px] w-[18px] text-emerald-400" />
      </div>
      <div>
        <h2 className="text-lg font-bold text-white leading-tight">{title}</h2>
        {sub && <p className="text-xs text-slate-500">{sub}</p>}
      </div>
    </div>
  )
}

function ServiceCard({ svc }: { svc: PlatformDiagnosticService }) {
  const s = STATUS_STYLE[svc.status] ?? STATUS_STYLE.unhealthy
  const Icon = SERVICE_ICONS[svc.service] ?? Server
  const lColor = svc.status === 'healthy' ? latencyColor(svc.latency_ms) : s.color
  const isSkipped = svc.status === 'skipped'

  return (
    <div
      className="rounded-xl p-4"
      style={{ background: s.bg, border: `1px solid ${s.border}` }}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: tint(s.color, 9.41), border: `1px solid ${tint(s.color, 18.82)}` }}
        >
          <Icon className="h-5 w-5" style={{ color: s.color }} />
        </div>
        <span
          className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide"
          style={{ background: tint(s.color, 9.41), color: s.color, border: `1px solid ${tint(s.color, 18.82)}` }}
        >
          {s.label}
        </span>
      </div>
      <p className="text-base font-bold text-white mb-0.5">{svc.label}</p>
      <p className="text-[11px] text-slate-500 font-mono mb-2">{svc.service}</p>
      {!isSkipped && (
        <p className="text-xs text-slate-500">
          Latency:{' '}
          <span className="font-semibold" style={{ color: lColor }}>
            {svc.service === 'api' ? 'local' : fmtLatency(svc.latency_ms)}
          </span>
        </p>
      )}
      {svc.detail && (
        <p className="text-[11px] text-slate-400 mt-1">{svc.detail}</p>
      )}
      {svc.error_msg && (
        <p className="text-[11px] text-red-400 mt-1 truncate" title={svc.error_msg}>
          {svc.error_msg}
        </p>
      )}
      {isSkipped && (
        <p className="text-[11px] text-slate-600 mt-1">Not configured</p>
      )}
    </div>
  )
}

function QueueKpi({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div
      className="rounded-xl p-4 flex items-center gap-4"
      style={{
        background: 'linear-gradient(135deg, var(--pc-t-surf3-90), var(--pc-t-surf4-90))',
        border: '1px solid var(--pc-t-overlay-07)',
      }}
    >
      <div
        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: tint(color, 9.41), border: `1px solid ${tint(color, 18.82)}` }}
      >
        <div className="w-3 h-3 rounded-full" style={{ background: color }} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-white leading-tight">{value.toLocaleString()}</p>
        <p className="text-xs text-slate-500 mt-0.5 uppercase tracking-wide font-semibold">{label}</p>
      </div>
    </div>
  )
}

function QueueRow({ label, pending, running, color }: { label: string; pending: number; running: number; color: string }) {
  return (
    <div className="flex items-center justify-between py-2.5" style={{ borderBottom: '1px solid var(--pc-t-overlay-04)' }}>
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full" style={{ background: color }} />
        <span className="text-sm font-semibold text-slate-300">{label}</span>
      </div>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-slate-500">
          Pending: <span className="font-bold" style={{ color: pending > 0 ? 'var(--pc-amber-400)' : 'var(--pc-slate-600)' }}>{pending}</span>
        </span>
        <span className="text-slate-500">
          Running: <span className="font-bold" style={{ color: running > 0 ? 'var(--pc-blue-400)' : 'var(--pc-slate-600)' }}>{running}</span>
        </span>
      </div>
    </div>
  )
}

function AICard({ p }: { p: AIProviderDiagnostic }) {
  const ready = p.status === 'ready'
  const active = p.active
  const color  = ready ? 'var(--pc-emerald-400)' : 'var(--pc-red-400)'
  const bg     = ready ? 'var(--pc-t-emerald-08)' : 'var(--pc-t-red-06)'
  const border = ready ? 'var(--pc-t-emerald-20)' : 'var(--pc-t-red-20)'

  return (
    <div className="rounded-xl p-4" style={{ background: bg, border: `1px solid ${border}` }}>
      <div className="flex items-start justify-between gap-2 mb-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
          style={{ background: tint(color, 9.41), border: `1px solid ${tint(color, 18.82)}` }}
        >
          <Bot className="h-5 w-5" style={{ color }} />
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
            style={{ background: tint(color, 9.41), color, border: `1px solid ${tint(color, 18.82)}` }}
          >
            {ready ? 'Ready' : 'Not configured'}
          </span>
        </div>
      </div>
      <p className="text-base font-bold text-white mb-0.5">{p.name}</p>
      <p className="text-[11px] text-slate-500 font-mono truncate">{p.model}</p>
      {!ready && (
        <p className="text-[11px] text-slate-600 mt-1">Set {p.provider_key.toUpperCase()}_API_KEY to enable</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function HealthPage() {
  const { data, isLoading, isError, refetch, isFetching, dataUpdatedAt } = useQuery({
    queryKey: ['platform-health'],
    queryFn: getPlatformHealth,
    staleTime: 30_000,
  })

  const allHealthy = data?.all_healthy ?? false
  const q = data?.queue as QueueDiagnostics | undefined

  return (
    <main className="max-w-screen-xl mx-auto px-8 py-8">

      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Platform Health</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Detailed diagnostics for all platform services — use this to troubleshoot issues
          </p>
        </div>
        <div className="flex items-center gap-3">
          {dataUpdatedAt > 0 && (
            <span className="text-xs text-slate-600 flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" />
              {new Date(dataUpdatedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold text-slate-300 disabled:opacity-50"
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            {isFetching ? 'Checking…' : 'Run Checks'}
          </button>
        </div>
      </div>

      {/* ── Overall status banner ────────────────────────────────────── */}
      {data && (
        <div
          className="rounded-xl px-5 py-4 mb-8 flex items-center gap-3"
          style={allHealthy
            ? { background: 'var(--pc-t-emerald-08)', border: '1px solid var(--pc-t-emerald-20)' }
            : { background: 'var(--pc-t-red-08)',  border: '1px solid var(--pc-t-red-25)' }}
        >
          {allHealthy
            ? <CheckCircle2 className="h-5 w-5 text-emerald-400 flex-shrink-0" />
            : <AlertTriangle className="h-5 w-5 text-red-400 flex-shrink-0" />}
          <div>
            <p className="text-sm font-bold" style={{ color: allHealthy ? 'var(--pc-emerald-400)' : 'var(--pc-red-400)' }}>
              {allHealthy ? 'All systems operational' : 'Degraded — one or more services need attention'}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              Last checked: {new Date(data.generated_at).toLocaleTimeString()}
              {' · '}Worker warnings do not affect system health.
            </p>
          </div>
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-24 text-slate-600">
          <RefreshCw className="h-5 w-5 animate-spin mr-2" />
          Running diagnostics…
        </div>
      )}

      {/* Error */}
      {isError && !isLoading && (
        <div
          className="rounded-xl px-5 py-4 mb-6 flex items-center gap-3"
          style={{ background: 'var(--pc-t-red-08)', border: '1px solid var(--pc-t-red-20)' }}
        >
          <AlertTriangle className="h-5 w-5 text-red-400 flex-shrink-0" />
          <p className="text-sm text-red-300">Failed to run health checks. Is the backend running?</p>
          <button
            onClick={() => refetch()}
            className="ml-auto text-xs text-slate-400 px-3 py-1.5 rounded-lg"
            style={{ background: 'var(--pc-t-overlay-05)', border: '1px solid var(--pc-t-overlay-10)' }}
          >
            Retry
          </button>
        </div>
      )}

      {data && (
        <div className="space-y-10">

          {/* ── 1. System Diagnostics ────────────────────────────────── */}
          <section>
            <SectionHeader
              icon={ShieldCheck}
              title="System Diagnostics"
              sub="Core infrastructure — database, cache, storage, vector DB, API"
            />
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              {data.system.map((svc) => (
                <ServiceCard key={svc.service} svc={svc} />
              ))}
            </div>
          </section>

          {/* ── 2. Worker + Queue ─────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">

            {/* Worker Diagnostics */}
            <section>
              <SectionHeader
                icon={Cpu}
                title="Worker Diagnostics"
                sub="Celery workers checked via broker ping"
              />
              <div className="grid grid-cols-2 gap-4 mb-3">
                {data.workers.map((svc) => (
                  <ServiceCard key={svc.service} svc={svc} />
                ))}
              </div>
              <p
                className="text-[11px] text-slate-600 px-3 py-2 rounded-lg"
                style={{ background: 'var(--pc-t-overlay-02)', border: '1px solid var(--pc-t-overlay-05)' }}
              >
                Workers checked by broadcast ping. In local dev, start workers with{' '}
                <span className="font-mono text-slate-500">celery -A app.workers.celery_app worker --pool=solo</span>.
                Warning status is non-critical.
              </p>
            </section>

            {/* Queue Diagnostics */}
            <section>
              <SectionHeader
                icon={Activity}
                title="Queue Diagnostics"
                sub={`${q?.workers_online ?? 0} worker(s) online · ${q?.total_24h ?? 0} tasks in last 24h`}
              />
              <div className="grid grid-cols-2 gap-3 mb-4">
                <QueueKpi label="Pending"    value={q?.pending ?? 0}    color="var(--pc-amber-400)" />
                <QueueKpi label="Running"    value={q?.running ?? 0}    color="var(--pc-blue-400)" />
                <QueueKpi label="Completed"  value={q?.completed ?? 0}  color="var(--pc-emerald-400)" />
                <QueueKpi label="Failed"     value={q?.failed ?? 0}     color="var(--pc-red-400)" />
              </div>
              <div
                className="rounded-xl px-4 py-1"
                style={{
                  background: 'linear-gradient(180deg, var(--pc-t-surf2-95) 0%, var(--pc-t-surf4-95) 100%)',
                  border: '1px solid var(--pc-t-overlay-08)',
                }}
              >
                <QueueRow label="celery (light)"  pending={q?.celery_pending ?? 0} running={q?.celery_running ?? 0} color="var(--pc-blue-400)" />
                <QueueRow label="celery-heavy (AI)" pending={q?.heavy_pending ?? 0} running={q?.heavy_running ?? 0} color="var(--pc-violet-400)" />
                <div className="flex items-center justify-between py-2.5">
                  <span className="text-xs text-slate-600 uppercase tracking-wide font-semibold">Failed (24h)</span>
                  <span
                    className="text-sm font-bold"
                    style={{ color: (q?.failed_24h ?? 0) > 0 ? 'var(--pc-red-400)' : 'var(--pc-slate-600)' }}
                  >
                    {q?.failed_24h ?? 0}
                  </span>
                </div>
              </div>
            </section>

          </div>

          {/* ── 3. AI Diagnostics ─────────────────────────────────────── */}
          <section>
            <SectionHeader
              icon={Bot}
              title="AI Diagnostics"
              sub="Provider configuration — API keys are never displayed"
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {data.ai.map((p) => (
                <AICard key={p.provider_key} p={p} />
              ))}
              <div
                className="rounded-xl p-4 flex flex-col items-center justify-center gap-2 col-span-1 sm:col-span-2 lg:col-span-2"
                style={{ background: 'var(--pc-t-overlay-02)', border: '1px dashed var(--pc-t-overlay-08)', minHeight: 80 }}
              >
                <Zap className="h-4 w-4 text-slate-700" />
                <p className="text-xs text-slate-700">Additional providers coming soon</p>
              </div>
            </div>
          </section>

        </div>
      )}
    </main>
  )
}
