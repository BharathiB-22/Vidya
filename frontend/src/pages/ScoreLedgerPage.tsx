// M09 Paper Administration — Score Ledger: Board-finalised results per exam paper (H-36 STEP-09/11)
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookLock, ChevronDown, ChevronUp, Download } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { PageLoading } from '@/components/shared/PageLoading'
import { PageEmpty } from '@/components/shared/PageEmpty'
import { Button } from '@/components/ui/button'
import { listLedgerForPaper, downloadLedgerCSV } from '@/lib/api/scripts'
import { listAllExamPapers } from '@/lib/api/exam'
import type { ExamScoreLedger } from '@/types/script'

export default function ScoreLedgerPage() {
  const [paperId, setPaperId]     = useState('')
  const [offset, setOffset]       = useState(0)
  const [exporting, setExporting] = useState(false)
  const limit = 50

  const { data: papersData } = useQuery({
    queryKey: ['exam-papers-released'],
    queryFn:  () => listAllExamPapers({ limit: 200 }),
  })

  const { data, isLoading } = useQuery({
    queryKey: ['score-ledger', paperId, offset],
    queryFn:  () => listLedgerForPaper(paperId, { offset, limit }),
    enabled:  !!paperId,
  })

  const items  = data?.items ?? []
  const total  = data?.total ?? 0
  const avgPct = items.length > 0
    ? (items.reduce((s, e) => s + (e.total_marks / e.max_marks) * 100, 0) / items.length).toFixed(1)
    : null

  return (
    <PageShell>
      <PageHeader
        icon={BookLock}
        title="Score Ledger"
        action={
          items.length > 0 ? (
            <Button
              variant="outline"
              size="sm"
              disabled={exporting}
              onClick={async () => {
                setExporting(true)
                try { await downloadLedgerCSV(paperId) }
                finally { setExporting(false) }
              }}
              className="gap-2"
            >
              <Download className="w-4 h-4" />
              {exporting ? 'Exporting…' : 'Export CSV'}
            </Button>
          ) : undefined
        }
      />

      {/* Paper selector */}
      <div className="max-w-md">
        <label className="block text-sm font-medium text-gray-700 mb-1">Exam Paper</label>
        <select
          value={paperId}
          onChange={e => { setPaperId(e.target.value); setOffset(0) }}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white"
        >
          <option value="">— Select exam paper —</option>
          {(papersData?.items ?? []).map(p => (
            <option key={p.id} value={p.id}>
              {p.title} · {p.exam_type.replace('_', ' ')} · {p.total_marks} marks
            </option>
          ))}
        </select>
      </div>

      {!paperId && (
        <PageEmpty icon={BookLock} message="Select an exam paper to view its finalised score ledger." />
      )}

      {paperId && isLoading && <PageLoading message="Loading ledger…" />}

      {paperId && !isLoading && items.length === 0 && (
        <PageEmpty icon={BookLock} message="No Board-finalised scripts found for this paper yet." />
      )}

      {items.length > 0 && (
        <>
          {/* Summary bar */}
          <div className="grid grid-cols-3 gap-3">
            <SummaryCard label="Scripts finalised" value={String(total)} />
            <SummaryCard
              label="Average score"
              value={avgPct != null ? `${avgPct}%` : '—'}
            />
            <SummaryCard
              label="Max marks"
              value={items[0]?.max_marks != null ? String(items[0].max_marks) : '—'}
            />
          </div>

          {/* Ledger table */}
          <div className="rounded-xl border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Masked ID</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Roll Ref</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Marks</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">%</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">Finalised</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {items.map(entry => (
                  <LedgerRow key={entry.id} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>

          {total > limit && (
            <div className="flex justify-between items-center pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - limit))}
              >
                Previous
              </Button>
              <span className="text-sm text-gray-500">
                Showing {Math.min(offset + 1, total)}–{Math.min(offset + limit, total)} of {total}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={offset + limit >= total}
                onClick={() => setOffset(offset + limit)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </PageShell>
  )
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 text-center">
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500 mt-1">{label}</p>
    </div>
  )
}

function LedgerRow({ entry }: { entry: ExamScoreLedger }) {
  const [expanded, setExpanded] = useState(false)
  const pct = entry.max_marks > 0
    ? ((entry.total_marks / entry.max_marks) * 100).toFixed(1)
    : '—'
  const pctNum = entry.max_marks > 0 ? (entry.total_marks / entry.max_marks) * 100 : null
  const pctColor = pctNum == null ? '' : pctNum >= 50 ? 'text-emerald-600' : 'text-red-600'

  return (
    <>
      <tr
        className="hover:bg-gray-50 cursor-pointer"
        onClick={() => setExpanded(v => !v)}
      >
        <td className="px-4 py-3 font-mono text-gray-700 text-sm">
          {entry.script_id.slice(0, 8)}…
        </td>
        <td className="px-4 py-3 text-gray-600">
          {entry.student_roll_ref ?? <span className="text-gray-400 italic text-xs">—</span>}
        </td>
        <td className="px-4 py-3 text-right font-semibold text-gray-800">
          {entry.total_marks} / {entry.max_marks}
        </td>
        <td className={`px-4 py-3 text-right font-semibold ${pctColor}`}>
          {pct}{pctNum != null ? '%' : ''}
        </td>
        <td className="px-4 py-3 text-xs text-gray-400 hidden md:table-cell">
          {new Date(entry.finalised_at).toLocaleString()}
          {expanded
            ? <ChevronUp className="w-3 h-3 inline ml-1" />
            : <ChevronDown className="w-3 h-3 inline ml-1" />}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-gray-50">
          <td colSpan={5} className="px-4 py-3">
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600">
              <p><span className="font-medium">Ledger ID:</span> <span className="font-mono">{entry.id}</span></p>
              <p><span className="font-medium">Script ID:</span> <span className="font-mono">{entry.script_id}</span></p>
              {entry.student_user_id && (
                <p><span className="font-medium">Student ID:</span> <span className="font-mono">{entry.student_user_id}</span></p>
              )}
              {entry.finalisation_note && (
                <p className="col-span-2"><span className="font-medium">Note:</span> {entry.finalisation_note}</p>
              )}
              <p><span className="font-medium">Finalised by:</span> <span className="font-mono text-xs">{entry.finalised_by}</span></p>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
