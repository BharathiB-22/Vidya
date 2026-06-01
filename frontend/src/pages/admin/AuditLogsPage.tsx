import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity, AlertTriangle, Bot, CheckCircle2, ChevronLeft, ChevronRight,
  Clock, Filter, Globe, LogIn, RefreshCw, ScrollText, ShieldAlert,
} from 'lucide-react'
import { getAuditStats, listAuditLogs } from '@/lib/api/auditLogs'
import type { AuditLogEntry } from '@/lib/api/auditLogs'
import { listTenants } from '@/lib/api/tenants'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50

const EVENT_TYPE_GROUPS: { label: string; types: string[] }[] = [
  {
    label: 'Authentication',
    types: [
      'AUTH_LOGIN_SUCCESS', 'AUTH_LOGIN_FAILURE', 'AUTH_LOGOUT', 'AUTH_LOGOUT_ALL',
      'AUTH_TOKEN_REFRESH', 'AUTH_TOKEN_REUSE_DETECTED',
      'AUTH_PASSWORD_RESET_REQUESTED', 'AUTH_PASSWORD_RESET_COMPLETED', 'AUTH_PASSWORD_CHANGED',
      'PLATFORM_LOGIN_SUCCESS', 'PLATFORM_LOGIN_FAILURE', 'PLATFORM_LOGOUT', 'PLATFORM_LOGOUT_ALL',
      'PLATFORM_TOKEN_REFRESH', 'PLATFORM_TOKEN_REUSE_DETECTED',
      'PLATFORM_PASSWORD_RESET_REQUESTED', 'PLATFORM_PASSWORD_RESET_COMPLETED',
    ],
  },
  {
    label: 'Tenant Management',
    types: [
      'TENANT_PROVISIONED', 'TENANT_UPDATED', 'TENANT_DEACTIVATED',
      'TENANT_ARCHIVED', 'TENANT_REACTIVATED', 'TENANT_DELETED',
    ],
  },
  {
    label: 'Users',
    types: ['USER_CREATED', 'USER_UPDATED', 'USER_DEACTIVATED', 'USER_ROLE_CHANGED'],
  },
  {
    label: 'Programs',
    types: [
      'PROGRAM_CREATED', 'PROGRAM_UPDATED', 'PROGRAM_DELETED',
      'PROGRAM_GENERATION_QUEUED', 'PROGRAM_GENERATION_COMPLETED', 'PROGRAM_GENERATION_FAILED',
      'PROGRAM_APPROVED', 'PROGRAM_REJECTED', 'PROGRAM_FORKED',
      'PROGRAM_COURSE_ADDED', 'PROGRAM_COURSE_DELETED', 'PROGRAM_EXPORT_COMPLETED',
    ],
  },
  {
    label: 'Syllabuses',
    types: [
      'SYLLABUS_CREATED', 'SYLLABUS_UPDATED', 'SYLLABUS_DELETED',
      'SYLLABUS_GENERATION_QUEUED', 'SYLLABUS_GENERATION_COMPLETED', 'SYLLABUS_GENERATION_FAILED',
      'SYLLABUS_APPROVED', 'SYLLABUS_REJECTED', 'SYLLABUS_LOCKED', 'SYLLABUS_FORKED',
      'REFERENCE_ENRICHMENT_COMPLETED', 'REFERENCE_ENRICHMENT_FAILED',
    ],
  },
  {
    label: 'Course Kits',
    types: [
      'COURSE_KIT_CREATED', 'COURSE_KIT_UPDATED', 'COURSE_KIT_DELETED',
      'COURSE_KIT_GENERATION_QUEUED', 'COURSE_KIT_GENERATION_COMPLETED', 'COURSE_KIT_GENERATION_FAILED',
      'COURSE_KIT_PUBLISHED', 'COURSE_KIT_ARCHIVED', 'COURSE_KIT_FORKED',
    ],
  },
  {
    label: 'Learning Packages',
    types: [
      'LEARNING_PACKAGE_CURATION_QUEUED', 'LEARNING_PACKAGE_CURATION_COMPLETED',
      'LEARNING_PACKAGE_CURATION_FAILED', 'LEARNING_PACKAGE_RAG_INDEXING_COMPLETED',
      'LEARNING_PACKAGE_ITEM_ADDED', 'LEARNING_PACKAGE_ITEM_REMOVED',
    ],
  },
  {
    label: 'Labs',
    types: [
      'LAB_ASSIGNMENT_CREATED', 'LAB_ASSIGNMENT_PUBLISHED', 'LAB_ASSIGNMENT_CLOSED',
      'LAB_SUBMISSION_RECEIVED', 'LAB_SUBMISSION_FLAGGED',
      'LAB_EVAL_QUEUED', 'LAB_EVAL_COMPLETED', 'LAB_EVAL_FAILED',
      'LAB_SCORES_UPDATED', 'LAB_SUBMISSION_RATIFIED',
    ],
  },
  {
    label: 'Research',
    types: [
      'RESEARCH_PROBLEM_SUBMITTED', 'RESEARCH_PROBLEM_AI_EVALUATED', 'RESEARCH_PROBLEM_GUIDE_DECIDED',
      'RESEARCH_DOCUMENT_SUBMITTED', 'RESEARCH_DOCUMENT_AI_EVALUATED', 'RESEARCH_DOCUMENT_GUIDE_REVIEWED',
      'VIVA_SESSION_SCHEDULED', 'VIVA_SESSION_STARTED', 'VIVA_SESSION_COMPLETED',
      'VIVA_AI_EVALUATED', 'VIVA_GUIDE_RATIFIED',
    ],
  },
  {
    label: 'Exams',
    types: [
      'EXAM_PAPER_CREATED', 'EXAM_PAPER_GENERATION_QUEUED', 'EXAM_PAPER_GENERATION_COMPLETED',
      'EXAM_PAPER_GENERATION_FAILED', 'EXAM_PAPER_SUBMITTED', 'EXAM_PAPER_BOARD_APPROVED',
      'EXAM_PAPER_BOARD_RETURNED', 'EXAM_PAPER_SEALED', 'EXAM_PAPER_RELEASED',
      'EXAM_PAPER_EXPORTED', 'EXAM_PAPER_EXPORT_PDF',
      'INTERNAL_MARKS_SUBMITTED', 'INTERNAL_MARKS_LOCKED',
      'QUESTION_BANK_PROMOTED',
    ],
  },
  {
    label: 'Scripts & Bell Curve',
    types: [
      'SCRIPT_QUALITY_CHECK_STARTED', 'SCRIPT_QUALITY_CHECK_COMPLETED',
      'SCRIPT_OCR_STARTED', 'SCRIPT_OCR_COMPLETED',
      'SCRIPT_SCORING_QUEUED', 'SCRIPT_SCORING_COMPLETED', 'SCRIPT_SCORING_FAILED',
      'SCRIPT_MARKS_SUBMITTED', 'SCRIPT_BOARD_FINALISED',
      'BELL_CURVE_ANALYSIS_TRIGGERED', 'BELL_CURVE_ANALYSIS_COMPLETED', 'BELL_CURVE_BOARD_RATIFIED',
    ],
  },
  {
    label: 'SIS',
    types: [
      'SCHOOL_CREATED', 'SCHOOL_UPDATED', 'SCHOOL_DELETED',
      'ENROLLMENT_CREATED', 'ENROLLMENT_UNENROLLED', 'ENROLLMENT_MOVED',
    ],
  },
  {
    label: 'Storage',
    types: ['STORAGE_ASSET_CREATED', 'STORAGE_ASSET_DOWNLOADED', 'STORAGE_ASSET_DELETED'],
  },
]

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatEventType(type: string): string {
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function formatSchemaName(schema: string | null): string {
  if (!schema) return '—'
  return schema
    .replace(/^tenant_/, '')
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function formatActor(entry: AuditLogEntry): string {
  const role = entry.actor_role ?? ''
  if (!entry.actor_user_id) return role || '—'
  const short = entry.actor_user_id.substring(0, 8)
  return role ? `${role} · ${short}…` : `${short}…`
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60)   return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60)   return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24)   return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function formatTs(iso: string): { date: string; time: string } {
  const d = new Date(iso)
  return {
    date: d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }),
    time: d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
  }
}

type EventStatus = 'success' | 'failed' | 'warning' | 'info'

function getEventStatus(type: string): EventStatus {
  if (
    /_SUCCESS$/.test(type) || /_COMPLETED$/.test(type) || /_PROVISIONED$/.test(type) ||
    /_APPROVED$/.test(type) || /_RATIFIED$/.test(type) || /_VERIFIED$/.test(type) ||
    /_CREATED$/.test(type) || /_PUBLISHED$/.test(type) || /_LOCKED$/.test(type) ||
    /_FORKED$/.test(type) || /_PROMOTED$/.test(type) || /_REACTIVATED$/.test(type)
  ) return 'success'

  if (
    /_FAILED$/.test(type) || /_FAILURE$/.test(type) ||
    /TOKEN_REUSE/.test(type) || /_OTP_FAILED$/.test(type)
  ) return 'failed'

  if (
    /_REJECTED$/.test(type) || /_DEACTIVATED$/.test(type) || /_ARCHIVED$/.test(type) ||
    /_RETURNED$/.test(type) || /_FLAGGED$/.test(type) || /_OVERRIDDEN$/.test(type) ||
    /_REVOKED$/.test(type) || /_UNENROLLED$/.test(type) || /_DELETED$/.test(type)
  ) return 'warning'

  return 'info'
}

const STATUS_STYLES: Record<EventStatus, { label: string; bg: string; color: string; border: string }> = {
  success: { label: 'SUCCESS', bg: 'rgba(16,185,129,0.12)', color: '#34d399', border: 'rgba(16,185,129,0.3)' },
  failed:  { label: 'FAILED',  bg: 'rgba(239,68,68,0.12)',  color: '#f87171', border: 'rgba(239,68,68,0.3)'  },
  warning: { label: 'WARNING', bg: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: 'rgba(251,191,36,0.3)' },
  info:    { label: 'ACTION',  bg: 'rgba(96,165,250,0.12)', color: '#60a5fa', border: 'rgba(96,165,250,0.3)' },
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function KpiCard({
  label, value, icon: Icon, color, sub,
}: {
  label: string; value: number | string; icon: typeof Activity; color: string; sub?: string
}) {
  return (
    <div
      className="rounded-xl p-4 flex items-center gap-4"
      style={{
        background: 'linear-gradient(135deg, rgba(15,26,48,0.9), rgba(10,18,35,0.9))',
        border: '1px solid rgba(255,255,255,0.07)',
        boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
      }}
    >
      <div
        className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0"
        style={{ background: color + '18', border: `1px solid ${color}30` }}
      >
        <Icon className="h-5 w-5" style={{ color }} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-white leading-tight">
          {typeof value === 'number' ? value.toLocaleString() : value}
        </p>
        <p className="text-xs font-semibold text-slate-400 mt-0.5 truncate">{label}</p>
        {sub && <p className="text-[11px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: EventStatus }) {
  const s = STATUS_STYLES[status]
  return (
    <span
      className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide whitespace-nowrap"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}
    >
      {s.label}
    </span>
  )
}

function RecentEventRow({ entry, tenantMap }: { entry: AuditLogEntry; tenantMap: Record<string, string> }) {
  const status = getEventStatus(entry.event_type)
  const s = STATUS_STYLES[status]
  const tenantName = entry.schema_name
    ? (tenantMap[entry.schema_name] ?? formatSchemaName(entry.schema_name))
    : null

  return (
    <div
      className="flex items-start gap-3 py-3"
      style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
    >
      <div
        className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
        style={{ background: s.bg, border: `1px solid ${s.border}` }}
      >
        {status === 'failed' ? (
          <AlertTriangle className="h-3.5 w-3.5" style={{ color: s.color }} />
        ) : status === 'success' ? (
          <CheckCircle2 className="h-3.5 w-3.5" style={{ color: s.color }} />
        ) : (
          <Activity className="h-3.5 w-3.5" style={{ color: s.color }} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-slate-200 leading-tight truncate">
          {formatEventType(entry.event_type)}
        </p>
        {tenantName && (
          <p className="text-[11px] text-slate-600 mt-0.5 truncate">{tenantName}</p>
        )}
        <p className="text-[11px] text-slate-700 mt-0.5">{timeAgo(entry.created_at)}</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const EMPTY_FILTERS = { tenant_id: '', event_type: '', date_from: '', date_to: '' }

export default function AuditLogsPage() {
  const [draft, setDraft]     = useState({ ...EMPTY_FILTERS })
  const [applied, setApplied] = useState({ ...EMPTY_FILTERS })
  const [page, setPage]       = useState(1)

  const statsQuery   = useQuery({ queryKey: ['audit-stats'],   queryFn: getAuditStats,   staleTime: 30_000, refetchInterval: 60_000 })
  const tenantsQuery = useQuery({ queryKey: ['tenants-list'],  queryFn: () => listTenants(true), staleTime: 300_000 })
  const logsQuery    = useQuery({
    queryKey: ['audit-logs', applied, page],
    queryFn: () => listAuditLogs({
      tenant_id:  applied.tenant_id  || undefined,
      event_type: applied.event_type || undefined,
      date_from:  applied.date_from  || undefined,
      date_to:    applied.date_to    || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    staleTime: 20_000,
  })

  const tenantMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (const t of tenantsQuery.data ?? []) map[t.schema_name] = t.name
    return map
  }, [tenantsQuery.data])

  const stats = statsQuery.data
  const logs  = logsQuery.data

  const totalPages = logs ? Math.max(1, Math.ceil(logs.total / PAGE_SIZE)) : 1

  function applyFilters() {
    setPage(1)
    setApplied({ ...draft })
  }

  function resetFilters() {
    setDraft({ ...EMPTY_FILTERS })
    setApplied({ ...EMPTY_FILTERS })
    setPage(1)
  }

  const hasFilters = Object.values(applied).some(Boolean)

  return (
    <main className="max-w-screen-2xl mx-auto px-8 py-8">

      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-white">Audit Logs</h1>
          <p className="text-sm text-slate-400 mt-0.5">
            Complete event history across all tenants — append-only, tamper-proof
          </p>
        </div>
        <div className="flex items-center gap-3">
          {statsQuery.dataUpdatedAt > 0 && (
            <span className="text-xs text-slate-600 flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" />
              {new Date(statsQuery.dataUpdatedAt).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => { statsQuery.refetch(); logsQuery.refetch() }}
            disabled={statsQuery.isFetching || logsQuery.isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold text-slate-300 transition-all disabled:opacity-50"
            style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${(statsQuery.isFetching || logsQuery.isFetching) ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── KPI Cards ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-8">
        <KpiCard label="Total Events"    value={stats?.total_events   ?? '—'} icon={ScrollText}  color="#6366f1" />
        <KpiCard label="Tenant Events"   value={stats?.tenant_events  ?? '—'} icon={Globe}        color="#10b981" />
        <KpiCard label="Login Events"    value={stats?.login_events   ?? '—'} icon={LogIn}        color="#60a5fa" />
        <KpiCard label="AI Events"       value={stats?.ai_events      ?? '—'} icon={Bot}          color="#a78bfa" />
        <KpiCard label="Security Events" value={stats?.security_events ?? '—'} icon={ShieldAlert}  color="#f87171" />
      </div>

      {/* ── Two-column: Filters + Table | Recent Activity ────────── */}
      <div className="flex gap-6 items-start">

        {/* Left: Filters + Table */}
        <div className="flex-1 min-w-0">

          {/* Filter Bar */}
          <div
            className="rounded-xl p-5 mb-5"
            style={{ background: 'rgba(14,24,45,0.9)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            <div className="flex items-center gap-2 mb-4">
              <Filter className="h-4 w-4 text-slate-500" />
              <span className="text-sm font-semibold text-slate-300">Filters</span>
              {hasFilters && (
                <span
                  className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wide ml-1"
                  style={{ background: 'rgba(99,102,241,0.15)', color: '#818cf8', border: '1px solid rgba(99,102,241,0.3)' }}
                >
                  Active
                </span>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
              {/* Tenant */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Tenant</label>
                <select
                  value={draft.tenant_id}
                  onChange={(e) => setDraft((d) => ({ ...d, tenant_id: e.target.value }))}
                  className="w-full rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                >
                  <option value="">All Tenants</option>
                  {(tenantsQuery.data ?? []).map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>

              {/* Event Type */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">Event Type</label>
                <select
                  value={draft.event_type}
                  onChange={(e) => setDraft((d) => ({ ...d, event_type: e.target.value }))}
                  className="w-full rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}
                >
                  <option value="">All Event Types</option>
                  {EVENT_TYPE_GROUPS.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.types.map((t) => (
                        <option key={t} value={t}>{formatEventType(t)}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </div>

              {/* Date From */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">From</label>
                <input
                  type="date"
                  value={draft.date_from}
                  onChange={(e) => setDraft((d) => ({ ...d, date_from: e.target.value }))}
                  className="w-full rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', colorScheme: 'dark' }}
                />
              </div>

              {/* Date To */}
              <div>
                <label className="block text-[11px] font-semibold text-slate-500 uppercase tracking-wide mb-1">To</label>
                <input
                  type="date"
                  value={draft.date_to}
                  onChange={(e) => setDraft((d) => ({ ...d, date_to: e.target.value }))}
                  className="w-full rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none"
                  style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', colorScheme: 'dark' }}
                />
              </div>
            </div>

            {/* Buttons */}
            <div className="flex gap-2 mt-4">
              <button
                onClick={applyFilters}
                className="px-4 py-2 rounded-lg text-sm font-semibold text-white transition-all"
                style={{ background: 'rgba(99,102,241,0.8)', border: '1px solid rgba(99,102,241,0.5)' }}
              >
                Apply Filters
              </button>
              {hasFilters && (
                <button
                  onClick={resetFilters}
                  className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-400 transition-all"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  Reset
                </button>
              )}
            </div>
          </div>

          {/* Table */}
          <div
            className="rounded-xl overflow-hidden"
            style={{ background: 'rgba(14,24,45,0.9)', border: '1px solid rgba(255,255,255,0.08)' }}
          >
            {/* Table header */}
            <div
              className="grid grid-cols-[140px_1fr_1fr_1fr_1fr_90px] gap-3 px-4 py-3 text-[11px] font-bold text-slate-600 uppercase tracking-widest"
              style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
            >
              <span>Timestamp</span>
              <span>Tenant</span>
              <span>User</span>
              <span>Action</span>
              <span>Entity</span>
              <span>Status</span>
            </div>

            {/* Loading */}
            {logsQuery.isLoading && (
              <div className="flex items-center justify-center py-16 text-slate-600">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                Loading events…
              </div>
            )}

            {/* Error */}
            {logsQuery.isError && !logsQuery.isLoading && (
              <div className="flex items-center gap-3 px-4 py-5">
                <AlertTriangle className="h-4 w-4 text-red-400 flex-shrink-0" />
                <p className="text-sm text-red-300">Failed to load audit logs.</p>
              </div>
            )}

            {/* Empty */}
            {logsQuery.data && logsQuery.data.items.length === 0 && (
              <div className="flex items-center justify-center py-16 text-slate-600">
                <p className="text-sm">No events match the current filters.</p>
              </div>
            )}

            {/* Rows */}
            {(logsQuery.data?.items ?? []).map((entry) => {
              const { date, time } = formatTs(entry.created_at)
              const status = getEventStatus(entry.event_type)
              const tenantName = entry.schema_name
                ? (tenantMap[entry.schema_name] ?? formatSchemaName(entry.schema_name))
                : '—'
              return (
                <div
                  key={entry.id}
                  className="grid grid-cols-[140px_1fr_1fr_1fr_1fr_90px] gap-3 px-4 py-3 text-sm items-center"
                  style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}
                >
                  {/* Timestamp */}
                  <div className="min-w-0">
                    <p className="text-xs font-mono text-slate-300 leading-tight">{date}</p>
                    <p className="text-[11px] font-mono text-slate-600 leading-tight">{time}</p>
                  </div>

                  {/* Tenant */}
                  <p className="text-xs text-slate-300 truncate" title={entry.schema_name ?? ''}>
                    {tenantName}
                  </p>

                  {/* User */}
                  <p className="text-xs text-slate-400 truncate font-mono" title={entry.actor_user_id ?? ''}>
                    {formatActor(entry)}
                  </p>

                  {/* Action */}
                  <p className="text-xs text-slate-200 truncate" title={entry.event_type}>
                    {formatEventType(entry.event_type)}
                  </p>

                  {/* Entity */}
                  <div className="min-w-0">
                    {entry.target_entity ? (
                      <p className="text-xs text-slate-400 truncate">
                        {entry.target_entity}
                        {entry.target_id && (
                          <span className="text-slate-600 ml-1 font-mono">
                            {entry.target_id.substring(0, 8)}…
                          </span>
                        )}
                      </p>
                    ) : (
                      <p className="text-xs text-slate-700">—</p>
                    )}
                  </div>

                  {/* Status */}
                  <div><StatusBadge status={status} /></div>
                </div>
              )
            })}
          </div>

          {/* Pagination */}
          {logs && logs.total > 0 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-xs text-slate-600">
                Showing{' '}
                <span className="text-slate-400 font-semibold">
                  {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, logs.total)}
                </span>{' '}
                of{' '}
                <span className="text-slate-400 font-semibold">{logs.total.toLocaleString()}</span> events
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="p-1.5 rounded-lg text-slate-500 disabled:opacity-30 transition-all"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="text-xs text-slate-500 px-2">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="p-1.5 rounded-lg text-slate-500 disabled:opacity-30 transition-all"
                  style={{ border: '1px solid rgba(255,255,255,0.08)' }}
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right: Recent Activity */}
        <div
          className="w-80 flex-shrink-0 rounded-xl overflow-hidden sticky top-4"
          style={{ background: 'rgba(14,24,45,0.9)', border: '1px solid rgba(255,255,255,0.08)' }}
        >
          <div
            className="px-4 py-3 flex items-center gap-2"
            style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}
          >
            <Activity className="h-4 w-4 text-emerald-400" />
            <span className="text-sm font-bold text-white">Recent Activity</span>
            <span
              className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-bold"
              style={{ background: 'rgba(16,185,129,0.1)', color: '#34d399', border: '1px solid rgba(16,185,129,0.2)' }}
            >
              Live
            </span>
          </div>

          <div className="px-4">
            {statsQuery.isLoading && (
              <div className="flex items-center justify-center py-10 text-slate-600">
                <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                <span className="text-xs">Loading…</span>
              </div>
            )}
            {(stats?.recent ?? []).length === 0 && !statsQuery.isLoading && (
              <p className="text-xs text-slate-700 py-8 text-center">No events recorded yet.</p>
            )}
            {(stats?.recent ?? []).map((entry) => (
              <RecentEventRow key={entry.id} entry={entry} tenantMap={tenantMap} />
            ))}
          </div>
        </div>

      </div>
    </main>
  )
}
