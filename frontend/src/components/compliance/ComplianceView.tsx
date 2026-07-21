// M09.9 Compliance & Audit — shared governance dashboard.
//
// One configurable view powers both the Admin and Board compliance dashboards.
// It answers the seven governance questions: who changed marks, when, why, from
// what value to what value, and who approved moderation / revaluation /
// publication.  Everything is read-only.
import { useState } from 'react'
import {
  ShieldCheck, Activity, Edit3, Scale, RotateCcw, Gavel, Megaphone,
  Search, Download, FileText, X, Clock, User,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageError } from '@/components/shared/PageError'
import { StatCard, SectionCard, EmptyState, BarList } from '@/components/analytics/charts'
import {
  useComplianceDashboard, useAuditTrail, useResultHistory,
  useReportNames, useReport,
} from '@/hooks/compliance/useCompliance'
import { downloadReportCsv } from '@/lib/api/compliance'
import type { TimelineEntry, TrailScope } from '@/types/compliance'

const CATEGORY_TONE: Record<string, string> = {
  MARK_CHANGE: 'bg-rose-100 text-rose-700',
  EVALUATION: 'bg-indigo-100 text-indigo-700',
  MODERATION: 'bg-amber-100 text-amber-700',
  REVALUATION: 'bg-teal-100 text-teal-700',
  BOARD_APPROVAL: 'bg-violet-100 text-violet-700',
  PUBLICATION: 'bg-green-100 text-green-700',
  ASSIGNMENT: 'bg-sky-100 text-sky-700',
  SCANNING: 'bg-gray-100 text-gray-600',
}

const SCOPES: { value: TrailScope; label: string; needsRef: boolean; placeholder?: string }[] = [
  { value: 'date_range', label: 'All events (date range)', needsRef: false },
  { value: 'script', label: 'By script', needsRef: true, placeholder: 'Script ID' },
  { value: 'student', label: 'By student', needsRef: true, placeholder: 'Student user ID' },
  { value: 'evaluator', label: 'By evaluator', needsRef: true, placeholder: 'Evaluator user ID' },
  { value: 'exam', label: 'By exam paper', needsRef: true, placeholder: 'Exam paper ID' },
]

const REPORT_LABELS: Record<string, string> = {
  publication_approval: 'Publication Approval Report',
  moderation: 'Moderation Report',
  revaluation: 'Revaluation Report',
  evaluator_activity: 'Evaluator Activity Report',
  board_approval: 'Board Approval History',
}

function fmt(ts: string | null): string {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString() } catch { return ts }
}

export function ComplianceView({
  title, subtitle,
}: { title: string; subtitle: string }) {
  const dash = useComplianceDashboard()

  // Search / filter state
  const [scope, setScope] = useState<TrailScope>('date_range')
  const [ref, setRef] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [submitted, setSubmitted] = useState<{ scope: TrailScope; ref: string } | null>(null)
  const [drillScript, setDrillScript] = useState<string | null>(null)
  const [report, setReport] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const trailParams = {
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    page_size: 100,
  }
  const trail = useAuditTrail(
    submitted?.scope ?? 'date_range',
    submitted?.ref || undefined,
    trailParams,
    submitted !== null,
  )
  const reportNames = useReportNames()
  const reportData = useReport(report)
  const history = useResultHistory(drillScript)

  if (dash.isLoading) return <PageLoading />
  if (dash.isError || !dash.data) return <PageError onRetry={dash.refetch} />

  const k = dash.data.kpis
  const scopeMeta = SCOPES.find((s) => s.value === scope)!

  const categoryItems = Object.entries(dash.data.category_counts)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([cat, n]) => ({ label: cat.replace(/_/g, ' '), value: n, display: String(n), tone: 'indigo' as const }))

  function runSearch() {
    if (scopeMeta.needsRef && !ref.trim()) return
    setSubmitted({ scope, ref: ref.trim() })
  }

  async function onExport(name: string) {
    setExporting(true)
    try { await downloadReportCsv(name) } finally { setExporting(false) }
  }

  return (
    <PageShell>
      <PageHeader icon={ShieldCheck} title={title} subtitle={subtitle} />

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard label="Total events" value={k.total_events} icon={Activity} colorClass="border-gray-100 bg-gray-50 text-gray-800" />
        <StatCard label="Mark changes" value={k.mark_changes} icon={Edit3} colorClass="border-rose-100 bg-rose-50 text-rose-800" />
        <StatCard label="Moderations" value={k.moderations} icon={Scale} colorClass="border-amber-100 bg-amber-50 text-amber-800" />
        <StatCard label="Revaluations" value={k.revaluations} icon={RotateCcw} colorClass="border-teal-100 bg-teal-50 text-teal-800" />
        <StatCard label="Board approvals" value={k.board_approvals} icon={Gavel} colorClass="border-violet-100 bg-violet-50 text-violet-800" />
        <StatCard label="Publications" value={k.publications} icon={Megaphone} colorClass="border-green-100 bg-green-50 text-green-800" />
        <StatCard label="Categories" value={Object.values(dash.data.category_counts).filter((n) => n > 0).length} icon={FileText} colorClass="border-indigo-100 bg-indigo-50 text-indigo-800" />
      </div>

      {/* Search + timeline */}
      <SectionCard title="Audit trail search" subtitle="Drill into who changed what, when and why" icon={Search}>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-gray-600">
            Scope
            <select
              className="mt-1 block rounded-md border border-gray-200 px-2 py-1.5 text-sm"
              value={scope}
              onChange={(e) => { setScope(e.target.value as TrailScope); setSubmitted(null) }}
            >
              {SCOPES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </label>
          {scopeMeta.needsRef && (
            <label className="text-xs text-gray-600">
              {scopeMeta.placeholder}
              <input
                className="mt-1 block w-64 rounded-md border border-gray-200 px-2 py-1.5 text-sm"
                value={ref}
                placeholder={scopeMeta.placeholder}
                onChange={(e) => setRef(e.target.value)}
              />
            </label>
          )}
          <label className="text-xs text-gray-600">
            From
            <input type="date" className="mt-1 block rounded-md border border-gray-200 px-2 py-1.5 text-sm"
              value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="text-xs text-gray-600">
            To
            <input type="date" className="mt-1 block rounded-md border border-gray-200 px-2 py-1.5 text-sm"
              value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <Button onClick={runSearch} className="gap-1.5"><Search className="h-3.5 w-3.5" /> Search</Button>
        </div>

        <div className="mt-2">
          {submitted === null && <EmptyState message="Choose a scope and search to view the audit trail" />}
          {submitted !== null && trail.isLoading && <PageLoading />}
          {submitted !== null && trail.data && (
            trail.data.entries.length === 0
              ? <EmptyState message="No governance events match this search" />
              : (
                <div className="space-y-1">
                  <p className="text-xs text-gray-500">{trail.data.total} event(s)</p>
                  <Timeline entries={trail.data.entries} onDrill={setDrillScript} />
                </div>
              )
          )}
        </div>
      </SectionCard>

      {/* Category breakdown + recent activity */}
      <div className="grid lg:grid-cols-2 gap-4">
        <SectionCard title="Events by category" icon={Activity}>
          {categoryItems.length ? <BarList items={categoryItems} /> : <EmptyState />}
        </SectionCard>
        <SectionCard title="Recent governance activity" icon={Clock}>
          {dash.data.recent_events.length
            ? <Timeline entries={dash.data.recent_events} onDrill={setDrillScript} />
            : <EmptyState message="No recent governance events" />}
        </SectionCard>
      </div>

      {/* Reports */}
      <SectionCard title="Compliance reports" subtitle="Auditor-ready exports" icon={FileText}>
        <div className="flex flex-wrap gap-2">
          {(reportNames.data ?? []).map((name) => (
            <div key={name} className="flex items-center gap-1 rounded-lg border border-gray-200 px-2 py-1">
              <button
                className={`text-xs font-medium px-2 py-1 rounded ${report === name ? 'bg-indigo-600 text-white' : 'text-gray-700 hover:bg-gray-50'}`}
                onClick={() => setReport(report === name ? null : name)}
              >
                {REPORT_LABELS[name] ?? name}
              </button>
              <button
                className="text-gray-600 hover:text-indigo-600 disabled:opacity-40"
                title="Export CSV"
                disabled={exporting}
                onClick={() => onExport(name)}
              >
                <Download className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </div>
        {report && (
          <div className="mt-3">
            {reportData.isLoading && <PageLoading />}
            {reportData.data && <ReportTable rows={reportData.data.rows} />}
          </div>
        )}
      </SectionCard>

      {drillScript && (
        <ResultHistoryDrawer
          scriptId={drillScript}
          onClose={() => setDrillScript(null)}
          data={history.data}
          loading={history.isLoading}
        />
      )}
    </PageShell>
  )
}

// ---------------------------------------------------------------------------
// Timeline list
// ---------------------------------------------------------------------------

function Timeline({ entries, onDrill }: { entries: TimelineEntry[]; onDrill: (scriptId: string) => void }) {
  return (
    <ul className="divide-y divide-gray-100">
      {entries.map((e) => {
        const isScript = e.target_entity === 'scanned_script' && e.target_id
        return (
          <li key={e.id} className="flex items-start gap-3 py-2">
            <span className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${CATEGORY_TONE[e.category] ?? 'bg-gray-100 text-gray-600'}`}>
              {e.category.replace(/_/g, ' ')}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-gray-800">{e.label}</p>
              <p className="text-xs text-gray-500 flex flex-wrap gap-x-2">
                <span className="inline-flex items-center gap-1"><User className="h-3 w-3" />{e.actor_name ?? e.actor_role ?? 'system'}</span>
                <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{fmt(e.occurred_at)}</span>
              </p>
            </div>
            {isScript && (
              <button className="shrink-0 text-xs text-indigo-600 hover:underline" onClick={() => onDrill(e.target_id as string)}>
                View history
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ---------------------------------------------------------------------------
// Generic report table
// ---------------------------------------------------------------------------

function ReportTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <EmptyState message="No rows for this report" />
  const cols = Object.keys(rows[0])
  return (
    <div className="overflow-x-auto rounded-lg border border-gray-100">
      <table className="min-w-full text-xs">
        <thead className="bg-gray-50 text-gray-600">
          <tr>{cols.map((c) => <th key={c} className="px-2 py-1.5 text-left font-medium">{c.replace(/_/g, ' ')}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rows.map((r, i) => (
            <tr key={i} className="hover:bg-gray-50">
              {cols.map((c) => <td key={c} className="px-2 py-1.5 text-gray-700 whitespace-nowrap">{r[c] == null ? '—' : String(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Result change history drawer (drill-down)
// ---------------------------------------------------------------------------

function ResultHistoryDrawer({
  scriptId, onClose, data, loading,
}: {
  scriptId: string
  onClose: () => void
  data?: import('@/types/compliance').ResultChangeHistory
  loading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30" onClick={onClose}>
      <div className="h-full w-full max-w-xl overflow-y-auto bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Result change history</h3>
          <button onClick={onClose} className="text-gray-600 hover:text-gray-700"><X className="h-4 w-4" /></button>
        </div>
        <p className="mt-0.5 text-xs text-gray-500">Script {data?.masked_id ?? scriptId}</p>

        {loading && <PageLoading />}
        {data && (
          <div className="mt-4 space-y-5">
            <div className="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600">
              Identity {data.student_revealed ? 'revealed (Board-finalised)' : 'masked (pre-finalisation)'}
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-700 mb-1.5">Recorded mark changes</h4>
              {data.recorded_changes.length === 0
                ? <EmptyState message="No field-level mark changes recorded yet" />
                : (
                  <ul className="space-y-1.5">
                    {data.recorded_changes.map((m) => (
                      <li key={m.id} className="rounded-lg border border-gray-100 px-3 py-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-gray-800">{m.change_type.replace(/_/g, ' ')}</span>
                          <span className="text-gray-500">{fmt(m.created_at)}</span>
                        </div>
                        <div className="mt-1 text-gray-600">
                          {m.previous_marks ?? '—'} → <span className="font-semibold">{m.new_marks ?? '—'}</span>
                          {m.delta != null && <span className={`ml-1 ${m.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}>({m.delta >= 0 ? '+' : ''}{m.delta})</span>}
                          {' '}/ {m.max_marks ?? '—'}
                          <span className="ml-2 text-gray-600">by {m.actor_name ?? m.actor_role ?? '—'}</span>
                        </div>
                        {m.reason && <p className="mt-0.5 text-gray-500 italic">“{m.reason}”</p>}
                      </li>
                    ))}
                  </ul>
                )}
            </div>

            <div>
              <h4 className="text-xs font-semibold text-gray-700 mb-1.5">Per-question value lineage</h4>
              {data.question_history.length === 0
                ? <EmptyState message="No evaluation lineage yet" />
                : (
                  <ul className="space-y-2">
                    {data.question_history.map((q) => (
                      <li key={q.question_id} className="rounded-lg border border-gray-100 px-3 py-2">
                        <p className="text-[11px] text-gray-600">Q {q.question_id.slice(0, 8)} · max {q.max_marks ?? '—'}</p>
                        <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                          {q.steps.map((s, i) => (
                            <span key={i} className="inline-flex items-center gap-1">
                              {i > 0 && <span className="text-gray-500">→</span>}
                              <span className="rounded bg-gray-100 px-1.5 py-0.5">
                                <span className="text-gray-500">{s.stage}</span> <b>{s.marks ?? '—'}</b>
                              </span>
                            </span>
                          ))}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
