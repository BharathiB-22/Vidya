import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Building2, CheckCircle2, Clock, Shield, AlertTriangle,
  PlusCircle, Activity, ScrollText, ChevronRight,
} from 'lucide-react'
import { listTenants } from '@/lib/api/tenants'
import type { Tenant, TenantStatus } from '@/lib/api/tenants'

function StatusBadge({ status }: { status: TenantStatus }) {
  const cfg: Record<TenantStatus, { bg: string; color: string; border: string }> = {
    ACTIVE:       { bg: 'rgba(16,185,129,0.1)',   color: '#34d399', border: 'rgba(16,185,129,0.2)' },
    PROVISIONING: { bg: 'rgba(245,158,11,0.1)',   color: '#fbbf24', border: 'rgba(245,158,11,0.2)' },
    FAILED:       { bg: 'rgba(239,68,68,0.1)',    color: '#f87171', border: 'rgba(239,68,68,0.2)'  },
    INACTIVE:     { bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: 'rgba(100,116,139,0.2)' },
    ARCHIVED:     { bg: 'rgba(120,113,108,0.12)', color: '#a8a29e', border: 'rgba(120,113,108,0.2)' },
    DELETED:      { bg: 'rgba(239,68,68,0.08)',   color: '#9ca3af', border: 'rgba(239,68,68,0.15)' },
  }
  const { bg, color, border } = cfg[status] ?? cfg.INACTIVE
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-bold"
      style={{ background: bg, color, border: `1px solid ${border}` }}
    >
      {status}
    </span>
  )
}

function KpiCard({
  label, value, sub, icon: Icon, accentColor,
}: {
  label: string; value: string | number; sub?: string; icon: typeof Building2; accentColor: string
}) {
  return (
    <div
      className="rounded-xl p-5 flex items-center gap-4"
      style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
    >
      <div
        className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: accentColor + '18', border: `1px solid ${accentColor}30` }}
      >
        <Icon className="h-5 w-5" style={{ color: accentColor }} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-slate-100 leading-tight">{value}</p>
        <p className="text-xs font-medium text-slate-500">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function QuickAction({
  label, icon: Icon, onClick, soon,
}: {
  label: string; icon: typeof Building2; onClick?: () => void; soon?: boolean
}) {
  return (
    <button
      onClick={soon ? undefined : onClick}
      disabled={soon}
      className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-150 group w-full disabled:opacity-40 disabled:cursor-not-allowed"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', color: '#cbd5e1' }}
      onMouseEnter={(e) => {
        if (!soon) {
          (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(16,185,129,0.2)'
          ;(e.currentTarget as HTMLButtonElement).style.background = 'rgba(16,185,129,0.04)'
        }
      }}
      onMouseLeave={(e) => {
        if (!soon) {
          (e.currentTarget as HTMLButtonElement).style.borderColor = 'rgba(255,255,255,0.06)'
          ;(e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.02)'
        }
      }}
    >
      <div
        className="p-1.5 rounded-lg flex-shrink-0"
        style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}
      >
        <Icon className={`h-4 w-4 ${soon ? 'text-slate-600' : 'text-emerald-400'}`} />
      </div>
      <span className="flex-1 text-left text-slate-300">{label}</span>
      {soon ? (
        <span
          className="text-[8px] px-1.5 py-0.5 rounded font-bold uppercase"
          style={{ background: 'rgba(255,255,255,0.04)', color: '#475569', border: '1px solid rgba(255,255,255,0.06)' }}
        >
          soon
        </span>
      ) : (
        <ChevronRight className="h-3.5 w-3.5 text-slate-600 group-hover:text-emerald-400 transition-colors" />
      )}
    </button>
  )
}

function RecentTenantRow({ tenant, onView }: { tenant: Tenant; onView: () => void }) {
  return (
    <tr
      className="cursor-pointer transition-colors"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(255,255,255,0.02)' }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = '' }}
      onClick={onView}
    >
      <td className="px-4 py-3">
        <div className="font-medium text-slate-200 text-sm">{tenant.name}</div>
        <div className="text-xs text-slate-600">{tenant.slug}</div>
      </td>
      <td className="px-4 py-3"><StatusBadge status={tenant.status} /></td>
      <td className="px-4 py-3 text-xs text-slate-500">
        {new Date(tenant.created_at).toLocaleDateString()}
      </td>
      <td className="px-4 py-3">
        <span
          className="text-[10px] px-1.5 py-0.5 rounded font-medium"
          style={{ color: tenant.is_active ? '#34d399' : '#475569' }}
        >
          {tenant.is_active ? 'Active' : 'Inactive'}
        </span>
      </td>
    </tr>
  )
}

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

export default function AdminDashboardPage() {
  const navigate = useNavigate()

  const { data: tenants, isLoading } = useQuery({
    queryKey: ['admin-tenants', true],
    queryFn:  () => listTenants(true),
  })

  const all          = tenants ?? []
  const activeCount  = all.filter((t) => t.is_active).length
  const pendingCount = all.filter((t) => t.status === 'PROVISIONING').length
  const failedCount  = all.filter((t) => t.status === 'FAILED').length
  const recentFive   = [...all].slice(0, 5)

  return (
    <div className="max-w-screen-xl mx-auto px-8 py-7 space-y-7">

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          {/* Brand row */}
          <div className="flex items-center gap-2.5 mb-3">
            <img
              src="/branding/sherpavector-logo.png"
              alt="SherpaVector"
              className="h-6 w-6 object-contain flex-shrink-0"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
            <span className="text-xs font-bold text-slate-300">SherpaVector</span>
            <span className="text-slate-700">·</span>
            <span className="text-xs font-bold text-slate-200">VIDYA <span className="text-emerald-400">AI</span></span>
            <span
              className="text-[9px] font-bold px-2 py-0.5 rounded uppercase tracking-wide"
              style={{ background: 'rgba(16,185,129,0.08)', color: '#6ee7b7', border: '1px solid rgba(16,185,129,0.15)' }}
            >
              Platform Console
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-100">
            {getGreeting()}, Super Admin
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Platform overview · {isLoading ? '…' : `${all.length} universities registered`}
          </p>
        </div>
        <div
          className="hidden sm:flex items-center gap-1.5 text-emerald-400 text-[11px] font-bold px-3 py-1.5 rounded-full whitespace-nowrap flex-shrink-0"
          style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)' }}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Platform Active
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
        <KpiCard
          label="Total Universities"
          value={isLoading ? '—' : all.length}
          icon={Building2}
          accentColor="#6366f1"
        />
        <KpiCard
          label="Active Tenants"
          value={isLoading ? '—' : activeCount}
          icon={CheckCircle2}
          accentColor="#10b981"
        />
        <KpiCard
          label="Pending Setup"
          value={isLoading ? '—' : pendingCount}
          icon={Clock}
          accentColor="#f59e0b"
          sub={pendingCount > 0 ? 'Provisioning…' : 'All clear'}
        />
        <KpiCard
          label="Platform Health"
          value={isLoading ? '—' : failedCount === 0 ? 'OK' : `${failedCount} Failed`}
          icon={failedCount === 0 ? Shield : AlertTriangle}
          accentColor={failedCount === 0 ? '#10b981' : '#ef4444'}
          sub={failedCount === 0 ? 'Operational' : 'Needs attention'}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-6">

        {/* Recent tenants */}
        <div
          className="rounded-xl overflow-hidden"
          style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
        >
          <div
            className="px-5 py-4 flex items-center justify-between"
            style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
          >
            <h2 className="text-sm font-semibold text-slate-200">Recent Universities</h2>
            <button
              onClick={() => navigate('/admin/tenants')}
              className="text-xs text-emerald-500 hover:text-emerald-400 font-medium transition-colors"
            >
              View all
            </button>
          </div>

          {isLoading ? (
            <div className="px-5 py-8 text-sm text-slate-500 text-center">Loading…</div>
          ) : recentFive.length === 0 ? (
            <div className="px-5 py-8 text-sm text-slate-500 text-center">
              No universities yet.{' '}
              <button
                onClick={() => navigate('/admin/tenants/new')}
                className="text-emerald-400 hover:underline font-medium"
              >
                Create one
              </button>
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead style={{ borderBottom: '1px solid rgba(255,255,255,0.06)', background: 'rgba(255,255,255,0.02)' }}>
                <tr>
                  {['Institution', 'Status', 'Created', 'Active'].map((h) => (
                    <th
                      key={h}
                      className="px-4 py-2.5 text-left text-[10px] font-semibold uppercase tracking-wide"
                      style={{ color: '#475569' }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentFive.map((t) => (
                  <RecentTenantRow
                    key={t.id}
                    tenant={t}
                    onView={() => navigate(`/admin/tenants/${t.id}`)}
                  />
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Quick actions + status */}
        <div className="space-y-4">
          <div
            className="rounded-xl p-5"
            style={{ background: 'rgba(12,22,41,0.8)', border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <h2 className="text-sm font-semibold text-slate-300 mb-4">Quick Actions</h2>
            <div className="space-y-2">
              <QuickAction label="Create University" icon={PlusCircle} onClick={() => navigate('/admin/tenants/new')} />
              <QuickAction label="View All Tenants"  icon={Building2}  onClick={() => navigate('/admin/tenants')} />
              <QuickAction label="Platform Health"   icon={Activity}   soon />
              <QuickAction label="Audit Logs"        icon={ScrollText} soon />
            </div>
          </div>

          {/* Platform status */}
          <div
            className="rounded-xl p-4"
            style={{
              background: failedCount === 0 ? 'rgba(16,185,129,0.05)' : 'rgba(239,68,68,0.05)',
              border: `1px solid ${failedCount === 0 ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
            }}
          >
            <div className="flex items-center gap-2 mb-1.5">
              {failedCount === 0
                ? <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                : <AlertTriangle className="h-4 w-4 text-red-500 flex-shrink-0" />
              }
              <p
                className="text-sm font-semibold"
                style={{ color: failedCount === 0 ? '#6ee7b7' : '#fca5a5' }}
              >
                {failedCount === 0 ? 'All systems operational' : 'Provisioning errors'}
              </p>
            </div>
            <p
              className="text-xs"
              style={{ color: failedCount === 0 ? '#059669' : '#f87171' }}
            >
              {failedCount === 0
                ? `${activeCount} of ${all.length} tenants active.`
                : `${failedCount} tenant(s) in FAILED state.`
              }
            </p>
            {failedCount > 0 && (
              <button
                className="mt-3 text-xs px-3 py-1.5 rounded-lg font-medium transition-colors"
                style={{ background: 'rgba(239,68,68,0.1)', color: '#fca5a5', border: '1px solid rgba(239,68,68,0.2)' }}
                onClick={() => navigate('/admin/tenants')}
              >
                View failed tenants
              </button>
            )}
          </div>
        </div>
      </div>

    </div>
  )
}
