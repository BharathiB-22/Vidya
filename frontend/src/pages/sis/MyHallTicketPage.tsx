import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Ticket, CheckCircle2, XCircle, AlertTriangle, Printer,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { sisApi } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'

function EligibilityBadge({ status }: { status: string }) {
  if (status === 'ELIGIBLE')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg font-semibold"
        style={{ background: 'rgba(34,197,94,0.12)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}>
        <CheckCircle2 size={14} /> Eligible
      </span>
    )
  if (status === 'CONDITIONAL')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg font-semibold"
        style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}>
        <AlertTriangle size={14} /> Conditional — verify with admin
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg font-semibold"
      style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
      <XCircle size={14} /> Not Eligible
    </span>
  )
}

export default function MyHallTicketPage() {
  const [semesterId, setSemesterId] = useState('')

  const semestersQ = useQuery({
    queryKey: ['semesters-all'],
    queryFn: () => academicsApi.listSemesters(),
  })

  const eligQ = useQuery({
    queryKey: ['my-eligibility', semesterId],
    queryFn: () => sisApi.getMyEligibility(semesterId),
    enabled: !!semesterId,
  })

  const elig = eligQ.data

  return (
    <PageShell>
      <PageHeader title="My Hall Ticket" icon={Ticket} />

      <div className="px-6 py-4 max-w-xl space-y-5">

        {/* Semester picker */}
        <div>
          <label className="block text-xs text-slate-400 mb-1">Select Semester</label>
          <select
            value={semesterId}
            onChange={e => setSemesterId(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">— Choose semester —</option>
            {(semestersQ.data ?? []).map(s => (
              <option key={s.id} value={s.id}>
                Semester {s.number}{s.label ? ` — ${s.label}` : ''}
              </option>
            ))}
          </select>
        </div>

        {eligQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}

        {eligQ.isError && (
          <div className="rounded-xl border border-red-500/20 bg-red-500/8 p-4">
            <p className="text-sm text-red-400">
              {(eligQ.error as any)?.response?.data?.detail?.message ?? 'Eligibility not computed yet for this semester.'}
            </p>
          </div>
        )}

        {elig && (
          <>
            {/* Status card */}
            <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <h2 className="text-base font-bold text-white">{elig.student_name}</h2>
                  {elig.usn && <p className="text-xs text-slate-500 font-mono mt-0.5">{elig.usn}</p>}
                  <p className="text-xs text-slate-400 mt-0.5">{elig.semester_name}</p>
                </div>
                <EligibilityBadge status={elig.status} />
              </div>
            </div>

            {/* Hall ticket number */}
            {elig.is_ticket_available && elig.hall_ticket_number && (
              <div className="rounded-2xl border border-blue-500/20 bg-blue-500/8 p-5">
                <div className="flex items-center gap-2 mb-1">
                  <Ticket size={16} className="text-blue-400" />
                  <p className="text-sm font-bold text-blue-400">Hall Ticket Number</p>
                </div>
                <p className="text-3xl font-black text-white font-mono tracking-widest mt-2">
                  {elig.hall_ticket_number}
                </p>
                <button
                  onClick={() => window.print()}
                  className="mt-3 flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300">
                  <Printer size={12} /> Print / Save
                </button>
              </div>
            )}

            {elig.status === 'NOT_ELIGIBLE' && elig.failure_reasons.length > 0 && (
              <div className="rounded-2xl border border-red-500/20 bg-red-500/8 p-5">
                <p className="text-sm font-bold text-red-400 mb-2">Why you are not eligible</p>
                <ul className="space-y-1">
                  {elig.failure_reasons.map((r, i) => (
                    <li key={i} className="text-xs text-red-300 flex items-start gap-1.5">
                      <span className="text-red-500 mt-0.5">•</span> {r}
                    </li>
                  ))}
                </ul>
                <p className="text-xs text-slate-500 mt-3">
                  Contact your Dean or Admin if you believe this is incorrect.
                </p>
              </div>
            )}

            {/* Checklist */}
            <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
              <h3 className="text-sm font-bold text-white mb-3">Eligibility Checklist</h3>
              <div className="space-y-0">
                {elig.checklist.map((c, i) => (
                  <div key={i} className="flex items-start gap-3 py-2.5 border-b border-white/5 last:border-0">
                    {c.passed
                      ? <CheckCircle2 size={14} className="text-green-400 mt-0.5 flex-shrink-0" />
                      : <XCircle size={14} className="text-red-400 mt-0.5 flex-shrink-0" />}
                    <div>
                      <p className="text-sm font-semibold text-white">{c.check_name}</p>
                      <p className="text-xs text-slate-400 mt-0.5">{c.detail}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {!semesterId && (
          <div className="flex flex-col items-center justify-center py-16 text-slate-500">
            <Ticket size={36} className="mb-3 opacity-30" />
            <p className="text-sm">Select a semester to view your hall ticket eligibility</p>
          </div>
        )}
      </div>
    </PageShell>
  )
}
