import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ShieldAlert, AlertTriangle, Info, CheckCircle2,
  ChevronDown, ChevronRight, RefreshCw,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { CheckResult, ValidationSeverity } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Severity helpers
// ---------------------------------------------------------------------------

const SEV_META: Record<ValidationSeverity, { icon: React.ElementType; color: string; bg: string; label: string }> = {
  ERROR:   { icon: ShieldAlert,    color: '#f87171', bg: 'rgba(239,68,68,0.08)',    label: 'Error' },
  WARNING: { icon: AlertTriangle,  color: '#fbbf24', bg: 'rgba(251,191,36,0.08)',   label: 'Warning' },
  INFO:    { icon: Info,           color: '#60a5fa', bg: 'rgba(96,165,250,0.08)',   label: 'Info' },
}

// ---------------------------------------------------------------------------
// Check card
// ---------------------------------------------------------------------------

function CheckCard({ check }: { check: CheckResult }) {
  const [expanded, setExpanded] = useState(check.count > 0)
  const meta = SEV_META[check.severity]
  const Icon = meta.icon
  const hasItems = check.count > 0

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{
        borderColor: hasItems ? `${meta.color}30` : 'rgba(255,255,255,0.06)',
        background: hasItems ? meta.bg : 'rgba(255,255,255,0.02)',
      }}
    >
      {/* Header row */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3.5 text-left"
        onClick={() => setExpanded(v => !v)}
      >
        <Icon size={17} style={{ color: hasItems ? meta.color : '#475569' }} className="flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-sm font-medium ${hasItems ? 'text-slate-200' : 'text-slate-500'}`}>
              {check.label}
            </span>
            {hasItems ? (
              <span
                className="text-xs font-bold px-2 py-0.5 rounded-full"
                style={{ background: `${meta.color}20`, color: meta.color }}
              >
                {check.count}
              </span>
            ) : (
              <span className="text-xs text-slate-600 flex items-center gap-1">
                <CheckCircle2 size={12} className="text-emerald-700" /> Clean
              </span>
            )}
          </div>
          <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">{check.description}</p>
        </div>
        {hasItems && (
          expanded
            ? <ChevronDown size={15} className="text-slate-500 flex-shrink-0" />
            : <ChevronRight size={15} className="text-slate-500 flex-shrink-0" />
        )}
      </button>

      {/* Item list */}
      {expanded && hasItems && (
        <div className="border-t px-4 py-2 space-y-1" style={{ borderColor: `${meta.color}20` }}>
          {check.items.map((item, i) => (
            <div key={i} className="flex items-start gap-2 py-1">
              <span className="text-slate-700 text-xs tabular-nums w-5 flex-shrink-0">{i + 1}.</span>
              <span className="text-xs text-slate-400 break-all">{item.detail}</span>
            </div>
          ))}
          {check.count > check.items.length && (
            <p className="text-xs text-slate-600 italic pt-1">
              … and {check.count - check.items.length} more (showing first {check.items.length})
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ValidationReportPage() {
  const { data, isLoading, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['sis-validation'],
    queryFn:  () => sisApi.getValidationReport(),
    staleTime: 60_000,
  })

  const errors   = data?.checks.filter(c => c.severity === 'ERROR'   && c.count > 0).length ?? 0
  const warnings = data?.checks.filter(c => c.severity === 'WARNING' && c.count > 0).length ?? 0
  const infos    = data?.checks.filter(c => c.severity === 'INFO'    && c.count > 0).length ?? 0
  const clean    = data ? data.checks.every(c => c.count === 0) : false

  const generatedAt = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null

  return (
    <PageShell>
      <PageHeader
        icon={ShieldAlert}
        title="Data Validation Report"
        subtitle="Identify and resolve data quality issues across the SIS"
        action={
          <Button variant="outline" size="sm" onClick={() => refetch()} className="gap-1.5">
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            {isFetching ? 'Running…' : 'Refresh'}
          </Button>
        }
      />

      {isLoading ? (
        <PageLoading message="Running validation checks…" />
      ) : (
        <>
          {/* Summary strip */}
          <div className="flex flex-wrap gap-3 items-center">
            {clean ? (
              <div className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm"
                style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.25)', color: '#34d399' }}>
                <CheckCircle2 size={15} />
                <span className="font-medium">All checks passed — no issues found</span>
              </div>
            ) : (
              <>
                {errors > 0 && (
                  <div className="px-4 py-2 rounded-lg text-sm"
                    style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)', color: '#f87171' }}>
                    <span className="font-bold">{errors}</span>
                    <span className="ml-1.5 text-xs opacity-70">Error{errors !== 1 ? 's' : ''}</span>
                  </div>
                )}
                {warnings > 0 && (
                  <div className="px-4 py-2 rounded-lg text-sm"
                    style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.25)', color: '#fbbf24' }}>
                    <span className="font-bold">{warnings}</span>
                    <span className="ml-1.5 text-xs opacity-70">Warning{warnings !== 1 ? 's' : ''}</span>
                  </div>
                )}
                {infos > 0 && (
                  <div className="px-4 py-2 rounded-lg text-sm"
                    style={{ background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.25)', color: '#60a5fa' }}>
                    <span className="font-bold">{infos}</span>
                    <span className="ml-1.5 text-xs opacity-70">Info</span>
                  </div>
                )}
              </>
            )}
            {generatedAt && (
              <span className="text-xs text-slate-600 ml-auto">Last run: {generatedAt}</span>
            )}
          </div>

          {/* Check cards — errors first, then warnings, then info */}
          <div className="space-y-3">
            {['ERROR', 'WARNING', 'INFO'].flatMap(sev =>
              (data?.checks ?? [])
                .filter(c => c.severity === sev)
                .map(check => <CheckCard key={check.check_id} check={check} />)
            )}
          </div>
        </>
      )}
    </PageShell>
  )
}
