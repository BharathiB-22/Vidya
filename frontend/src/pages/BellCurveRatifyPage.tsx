// M10 Bell Curve Normaliser — Board Ratification Gate 1
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ChevronLeft, Loader2, AlertTriangle, Info, CheckCircle2,
  XCircle, Eye,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  getAnalysis,
  previewNormalisation,
  ratifyAnalysis,
} from '@/lib/api/bellCurve'
import { getErrorMessage } from '@/lib/api'
import type {
  BoardDecision,
  NormalisationMethod,
  PreviewNormalisationResponse,
} from '@/types/bellCurve'
import { useWorkspace } from '@/lib/workspace'

// ---------------------------------------------------------------------------
// Method descriptions
// ---------------------------------------------------------------------------

const METHOD_DESCRIPTIONS: Record<NormalisationMethod, string> = {
  NONE:          'Keep raw scores unchanged. Equivalent to rejection of normalisation.',
  LINEAR_SCALE:  'Multiply each score by a constant factor (capped at max marks).',
  PERCENTILE_MAP:'Map scores to a target distribution by percentile rank.',
  BOUNDARY_SHIFT:'Shift grade boundaries without changing raw scores.',
  CUSTOM:        'Board-supplied per-student score adjustments (deltas).',
}

// ---------------------------------------------------------------------------
// Method param fields
// ---------------------------------------------------------------------------

function MethodParams({
  method,
  params,
  setParams,
}: {
  method:    NormalisationMethod
  params:    Record<string, unknown>
  setParams: (p: Record<string, unknown>) => void
}) {
  const num = (key: string, label: string, min?: number, max?: number) => (
    <div className="space-y-1">
      <label className="text-xs font-medium text-gray-600">{label}</label>
      <input
        type="number"
        value={(params[key] as number) ?? ''}
        min={min}
        max={max}
        step="0.01"
        onChange={e => setParams({ ...params, [key]: parseFloat(e.target.value) })}
        className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
      />
    </div>
  )

  if (method === 'LINEAR_SCALE') {
    return (
      <div className="space-y-3">
        {num('scale_factor', 'Scale factor (e.g. 1.15 = +15%)', 0.1, 5)}
      </div>
    )
  }
  if (method === 'PERCENTILE_MAP') {
    return (
      <div className="grid grid-cols-2 gap-3">
        {num('target_mean', 'Target mean', 0, 100)}
        {num('target_max',  'Target max',  0, 100)}
      </div>
    )
  }
  if (method === 'BOUNDARY_SHIFT') {
    return (
      <div className="grid grid-cols-2 gap-3">
        {num('shift_amount', 'Shift amount', 0, 50)}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Direction</label>
          <select
            value={(params.direction as string) ?? 'UP'}
            onChange={e => setParams({ ...params, direction: e.target.value })}
            className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
          >
            <option value="UP">UP</option>
            <option value="DOWN">DOWN</option>
          </select>
        </div>
      </div>
    )
  }
  if (method === 'NONE') {
    return (
      <p className="text-xs text-gray-400">No parameters required for NONE method.</p>
    )
  }
  if (method === 'CUSTOM') {
    return (
      <p className="text-xs text-gray-400">
        Custom adjustments are not editable in this UI. Use the API directly to supply
        per-student deltas.
      </p>
    )
  }
  return null
}

// ---------------------------------------------------------------------------
// Preview result panel
// ---------------------------------------------------------------------------

function PreviewPanel({ preview }: { preview: PreviewNormalisationResponse }) {
  const ps = preview.projected_stats
  return (
    <div className="rounded-xl border border-teal-200 bg-teal-50 p-4 space-y-3">
      <h3 className="text-sm font-semibold text-teal-800 flex items-center gap-2">
        <Eye className="w-4 h-4" />
        Preview — Projected distribution
      </h3>
      <div className="grid grid-cols-3 gap-2 text-xs">
        {[
          ['Mean',   ps.mean.toFixed(2)],
          ['Median', ps.median.toFixed(2)],
          ['Std',    ps.std.toFixed(2)],
          ['Min',    ps.min.toFixed(1)],
          ['Max',    ps.max.toFixed(1)],
          ['Skew',   ps.skewness.toFixed(3)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg bg-white border border-teal-100 p-2 text-center">
            <div className="font-bold text-teal-800">{value}</div>
            <div className="text-teal-600">{label}</div>
          </div>
        ))}
      </div>

      {preview.score_deltas.length > 0 && (
        <div className="space-y-1 max-h-40 overflow-y-auto">
          <p className="text-xs font-medium text-teal-700">
            Score deltas ({preview.score_deltas.length} students)
          </p>
          {preview.score_deltas.slice(0, 20).map((d, i) => (
            <div key={i} className="flex justify-between text-xs text-teal-800 bg-white rounded px-2 py-1">
              <span className="font-mono">{d.student_roll_ref || '—'}</span>
              <span>{d.raw.toFixed(1)} → {d.normalised.toFixed(1)}</span>
              <span className={d.normalised >= d.raw ? 'text-green-600' : 'text-red-600'}>
                {d.normalised >= d.raw ? '+' : ''}{(d.normalised - d.raw).toFixed(2)}
              </span>
            </div>
          ))}
          {preview.score_deltas.length > 20 && (
            <p className="text-xs text-teal-500">…and {preview.score_deltas.length - 20} more</p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function BellCurveRatifyPage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()

  const { activeWorkspace: role } = useWorkspace()
  if (role !== 'BOARD') {
    return (
      <div className="max-w-xl mx-auto p-8 text-center text-gray-500">
        <AlertTriangle className="w-8 h-8 text-orange-400 mx-auto mb-3" />
        <p className="text-sm">Only Board members can access this page.</p>
      </div>
    )
  }

  const [method,  setMethod]  = useState<NormalisationMethod>('NONE')
  const [params,  setParams]  = useState<Record<string, unknown>>({})
  const [decision, setDecision] = useState<BoardDecision>('ACCEPTED_SUGGESTION')
  const [note,    setNote]    = useState('')
  const [preview, setPreview] = useState<PreviewNormalisationResponse | null>(null)
  const [confirmVisible, setConfirmVisible] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  const { data: analysis, isLoading, isError } = useQuery({
    queryKey: ['bell-curve-analysis', id],
    queryFn:  () => getAnalysis(id!),
    enabled:  !!id,
  })

  const previewMut = useMutation({
    mutationFn: () => previewNormalisation(id!, { method, params }),
    onSuccess:  (data) => { setPreview(data); setError(null) },
    onError:    (err)  => setError(getErrorMessage(err)),
  })

  const ratifyMut = useMutation({
    mutationFn: () => ratifyAnalysis(id!, {
      decision,
      normalisation_method: decision === 'REJECTED' ? 'NONE' : method,
      normalisation_params: decision === 'REJECTED' ? {} : params,
      ratification_note:    note.trim() || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bell-curve-analysis', id] })
      qc.invalidateQueries({ queryKey: ['bell-curve-analyses'] })
      navigate(`/bell-curve/${id}`)
    },
    onError: (err) => { setError(getErrorMessage(err)); setConfirmVisible(false) },
  })

  if (isLoading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
    </div>
  )
  if (isError || !analysis) return (
    <div className="max-w-4xl mx-auto p-6 text-red-600 text-sm">Failed to load analysis.</div>
  )

  const canRatify = analysis.status === 'READY' || analysis.status === 'BOARD_REVIEWED'
  const alreadyDone = analysis.status === 'APPLIED' || analysis.status === 'NO_ACTION'

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">

      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => navigate(`/bell-curve/${id}`)}>
          <ChevronLeft className="w-5 h-5" />
        </Button>
        <div>
          <h1 className="text-xl font-bold text-gray-900">Gate 1 — Board Ratification</h1>
          <p className="text-xs text-gray-400 font-mono mt-0.5 truncate">Analysis {id}</p>
        </div>
      </div>

      {/* Advisory */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 flex gap-3 text-sm text-blue-800">
        <Info className="w-4 h-4 shrink-0 mt-0.5 text-blue-600" />
        <span>
          <strong>Advisory only.</strong> This action records normalised scores in a separate table.
          Raw M09 marks in <code className="bg-blue-100 px-1 rounded">exam_score_ledger</code> are
          never modified. This action is irreversible once confirmed.
        </span>
      </div>

      {/* Already ratified */}
      {alreadyDone && (
        <div className={`rounded-xl border p-4 flex gap-3 text-sm ${
          analysis.status === 'APPLIED'
            ? 'border-green-200 bg-green-50 text-green-800'
            : 'border-orange-200 bg-orange-50 text-orange-800'
        }`}>
          {analysis.status === 'APPLIED'
            ? <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5 text-green-600" />
            : <XCircle className="w-4 h-4 shrink-0 mt-0.5 text-orange-600" />}
          <span>
            {analysis.status === 'APPLIED'
              ? 'This analysis has already been ratified. Normalised scores are recorded.'
              : 'This analysis has no-action set. Raw scores stand.'}
          </span>
        </div>
      )}

      {/* Raw stats summary */}
      {analysis.raw_stats && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2">
          <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Raw score summary</p>
          <div className="grid grid-cols-4 gap-2 text-center text-xs">
            {[
              ['Mean',   analysis.raw_stats.mean.toFixed(2)],
              ['Median', analysis.raw_stats.median.toFixed(2)],
              ['Std',    analysis.raw_stats.std.toFixed(2)],
              ['n',      String(analysis.score_count ?? '—')],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg border border-gray-100 p-2">
                <div className="font-bold text-gray-800">{value}</div>
                <div className="text-gray-400">{label}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI suggestion reminder */}
      {analysis.normalisation_suggestion && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50 p-3 flex gap-2 text-xs text-indigo-800">
          <Info className="w-3.5 h-3.5 shrink-0 mt-0.5 text-indigo-500" />
          <span>
            <strong>AI suggestion:</strong>{' '}
            {analysis.normalisation_suggestion.method.replace(/_/g, ' ')} — {' '}
            {analysis.normalisation_suggestion.reasoning}
          </span>
        </div>
      )}

      {/* Ratification form */}
      {!alreadyDone && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
          <p className="text-sm font-semibold text-gray-700">Board decision</p>

          {/* Decision selector */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Decision</label>
            <select
              value={decision}
              onChange={e => { setDecision(e.target.value as BoardDecision); setPreview(null) }}
              className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
            >
              <option value="ACCEPTED_SUGGESTION">Accept AI Suggestion</option>
              <option value="MODIFIED">Modified (custom params)</option>
              <option value="REJECTED">Reject normalisation (raw scores stand)</option>
            </select>
          </div>

          {/* Method selector */}
          {decision !== 'REJECTED' && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Normalisation method</label>
              <select
                value={method}
                onChange={e => { setMethod(e.target.value as NormalisationMethod); setParams({}); setPreview(null) }}
                className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              >
                {(['LINEAR_SCALE', 'PERCENTILE_MAP', 'BOUNDARY_SHIFT', 'NONE', 'CUSTOM'] as NormalisationMethod[]).map(m => (
                  <option key={m} value={m}>{m.replace(/_/g, ' ')}</option>
                ))}
              </select>
              <p className="text-xs text-gray-400">{METHOD_DESCRIPTIONS[method]}</p>
            </div>
          )}

          {/* Method params */}
          {decision !== 'REJECTED' && method !== 'NONE' && (
            <MethodParams method={method} params={params} setParams={setParams} />
          )}

          {/* Ratification note */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-gray-600">Ratification note (optional)</label>
            <textarea
              value={note}
              onChange={e => setNote(e.target.value)}
              rows={2}
              placeholder="Board justification or remarks…"
              className="w-full border border-gray-200 rounded-lg px-3 py-1.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-300"
            />
          </div>

          {/* Error */}
          {error && (
            <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              {error}
            </div>
          )}

          {/* Preview button */}
          {decision !== 'REJECTED' && method !== 'NONE' && (
            <Button
              variant="outline" size="sm"
              onClick={() => previewMut.mutate()}
              disabled={previewMut.isPending}
              className="gap-1.5"
            >
              {previewMut.isPending
                ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                : <Eye className="w-3.5 h-3.5" />}
              Preview projection (no DB write)
            </Button>
          )}
        </div>
      )}

      {/* Preview result */}
      {preview && <PreviewPanel preview={preview} />}

      {/* Confirm gate */}
      {!alreadyDone && canRatify && (
        confirmVisible ? (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5 space-y-3">
            <p className="text-sm font-semibold text-emerald-800">
              Confirm: {decision.replace(/_/g, ' ')} for this analysis?
            </p>
            <p className="text-xs text-emerald-700">
              {decision === 'REJECTED'
                ? 'Normalisation will be rejected. Raw M09 marks stand unchanged.'
                : `Normalised scores will be recorded using ${method.replace(/_/g, ' ')}.
                   This action cannot be undone.`}
            </p>
            {error && (
              <div className="flex gap-2 bg-red-50 border border-red-200 rounded-lg p-2 text-xs text-red-600">
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                {error}
              </div>
            )}
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={() => ratifyMut.mutate()}
                disabled={ratifyMut.isPending}
                className={`gap-1.5 text-white ${
                  decision === 'REJECTED'
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {ratifyMut.isPending
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <CheckCircle2 className="w-3.5 h-3.5" />}
                {decision === 'REJECTED' ? 'Confirm rejection' : 'Confirm ratification'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => { setConfirmVisible(false); setError(null) }}
                disabled={ratifyMut.isPending}
              >
                Cancel
              </Button>
            </div>
          </div>
        ) : (
          <Button
            className={`w-full gap-2 text-white ${
              decision === 'REJECTED'
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-indigo-600 hover:bg-indigo-700'
            }`}
            onClick={() => { setError(null); setConfirmVisible(true) }}
          >
            <CheckCircle2 className="w-4 h-4" />
            {decision === 'REJECTED' ? 'Reject normalisation' : 'Ratify decision (Gate 1)'}
          </Button>
        )
      )}
    </div>
  )
}
