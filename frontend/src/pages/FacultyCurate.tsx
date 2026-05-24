/**
 * FacultyCurate.tsx — Faculty package curation management page (STEP-16).
 *
 * Route: /learning-packages/:id/curate
 *
 * Features:
 *   - Package header with status badge and pipeline stepper
 *   - Trigger curation and RAG indexing with live job feedback
 *   - Items list: source badge, title, relevance, Faculty Pick toggle, remove
 *   - Inline add-faculty-resource form
 *   - Auto-polls package status while CURATING or job active
 */

import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  AlertTriangle,
  CheckCircle2,
  Circle,
  Database,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Star,
  Trash2,
  Zap,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PackageStatusBadge } from '@/components/learningPackage/PackageStatusBadge'
import {
  learningPackageKeys,
  useAddFacultyItem,
  useLearningPackage,
  usePackageItems,
  usePackageJob,
  useRemoveItem,
  useToggleRecommendation,
  useTriggerCuration,
  useTriggerIndexing,
} from '@/hooks/learningPackage'
import type {
  FacultyAddItemPayload,
  JobStatus,
  MaterialSourceType,
  PackageItem,
  PackageStatus,
} from '@/types/learningPackage'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SOURCE_LABELS: Record<MaterialSourceType, string> = {
  YOUTUBE:      'YouTube',
  ARXIV:        'arXiv',
  NPTEL:        'NPTEL',
  MIT_OCW:      'MIT OCW',
  FACULTY_NOTE: 'Faculty Note',
}

const ALL_SOURCE_TYPES: MaterialSourceType[] = [
  'YOUTUBE', 'ARXIV', 'NPTEL', 'MIT_OCW', 'FACULTY_NOTE',
]

const PIPELINE: Array<{ status: PackageStatus; label: string }> = [
  { status: 'PENDING',  label: 'Pending'  },
  { status: 'CURATING', label: 'Curating' },
  { status: 'READY',    label: 'Ready'    },
]

const STATUS_ORDER: Partial<Record<PackageStatus, number>> = {
  PENDING: 0, CURATING: 1, READY: 2, OUTDATED: 2,
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function PackageStepper({ status }: { status: PackageStatus }) {
  const current = STATUS_ORDER[status] ?? 0
  return (
    <div className="flex items-center gap-0 flex-wrap">
      {PIPELINE.map((step, idx) => {
        const order  = STATUS_ORDER[step.status] ?? 0
        const done   = order < current
        const active = step.status === status || (status === 'OUTDATED' && step.status === 'READY')
        return (
          <div key={step.status} className="flex items-center">
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
              active && status === 'OUTDATED' ? 'bg-orange-100 text-orange-700'
              : active ? 'bg-blue-100 text-blue-700'
              : done   ? 'bg-green-50 text-green-600'
              :          'text-gray-400'
            }`}>
              {done ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : active && step.status === 'CURATING' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : active ? (
                <Zap className="h-3.5 w-3.5" />
              ) : (
                <Circle className="h-3.5 w-3.5" />
              )}
              {step.label}
            </div>
            {idx < PIPELINE.length - 1 && (
              <div className={`h-px w-6 shrink-0 ${order + 1 <= current ? 'bg-green-200' : 'bg-gray-200'}`} />
            )}
          </div>
        )
      })}
      {status === 'OUTDATED' && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700 ml-1">
          <RefreshCw className="h-3.5 w-3.5" />
          Outdated
        </div>
      )}
    </div>
  )
}

function JobBanner({ job }: { job: JobStatus | undefined }) {
  if (!job) return null
  const { status, message, error, result } = job
  if (status === 'PENDING' || status === 'RUNNING') {
    return (
      <div className="flex items-center gap-2 rounded-lg bg-blue-50 border border-blue-200 px-4 py-3 text-blue-700 text-sm">
        <Loader2 className="h-4 w-4 animate-spin shrink-0" />
        <span>{status === 'PENDING' ? 'Job queued…' : (message ?? 'Processing…')}</span>
      </div>
    )
  }
  if (status === 'SUCCESS') {
    const warning = typeof result?.warning === 'string' ? result.warning : null
    if (warning) {
      return (
        <div className="flex items-start gap-2 rounded-lg bg-amber-50 border border-amber-200 px-4 py-3 text-amber-800 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
          <span>{warning}</span>
        </div>
      )
    }
    return (
      <div className="flex items-center gap-2 rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-green-700 text-sm">
        <CheckCircle2 className="h-4 w-4 shrink-0" />
        <span>Job completed successfully.</span>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2 rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-red-700 text-sm">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>{error ?? 'Job failed. Please retry.'}</span>
    </div>
  )
}

function RelevancePill({ score }: { score: number | null }) {
  if (score === null) return null
  const pct = Math.round(score * 100)
  return (
    <span className="text-[11px] tabular-nums text-gray-400 whitespace-nowrap">{pct}%</span>
  )
}

function ItemCurateRow({
  item,
  onToggle,
  onRemove,
  toggling,
  removing,
  readOnly = false,
}: {
  item:      PackageItem
  onToggle:  (value: boolean) => void
  onRemove:  () => void
  toggling:  boolean
  removing:  boolean
  readOnly?: boolean
}) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors group">
      {/* Source badge */}
      <Badge variant="outline" className="shrink-0 text-[11px] font-medium">
        {SOURCE_LABELS[item.source_type]}
      </Badge>

      {/* Title + meta */}
      <div className="flex-1 min-w-0">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-gray-800 hover:text-blue-700 hover:underline underline-offset-2 flex items-center gap-1 group/link"
          >
            <span className="line-clamp-1">{item.title}</span>
            <ExternalLink className="h-3 w-3 shrink-0 text-gray-300 group-hover/link:text-blue-500" />
          </a>
        ) : (
          <p className="text-sm font-medium text-gray-800 line-clamp-1">{item.title}</p>
        )}
      </div>

      {/* Relevance */}
      <RelevancePill score={item.relevance_score} />

      {/* Faculty recommended indicator / toggle */}
      {readOnly ? (
        item.faculty_recommended && (
          <Star className="h-4 w-4 shrink-0 text-amber-400 fill-current" />
        )
      ) : (
        <button
          type="button"
          title={item.faculty_recommended ? 'Remove Faculty Pick' : 'Mark as Faculty Pick'}
          disabled={toggling}
          onClick={() => onToggle(!item.faculty_recommended)}
          className={`shrink-0 rounded-md p-1 transition-colors ${
            item.faculty_recommended
              ? 'text-amber-500 hover:text-amber-600'
              : 'text-gray-300 hover:text-amber-400'
          } disabled:opacity-50`}
        >
          {toggling ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Star className={`h-4 w-4 ${item.faculty_recommended ? 'fill-current' : ''}`} />
          )}
        </button>
      )}

      {/* Remove — hidden for read-only */}
      {!readOnly && (
        <button
          type="button"
          title="Remove item"
          disabled={removing}
          onClick={onRemove}
          className="shrink-0 rounded-md p-1 text-gray-300 hover:text-red-500 transition-colors disabled:opacity-50"
        >
          {removing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </button>
      )}
    </div>
  )
}

function AddItemForm({
  packageId,
  onClose,
}: {
  packageId: string
  onClose:   () => void
}) {
  const addMutation = useAddFacultyItem(packageId)
  const [form, setForm] = useState<FacultyAddItemPayload>({
    source_type: 'FACULTY_NOTE',
    title:       '',
    url:         '',
  })
  const [formError, setFormError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const title = form.title.trim()
    if (title.length < 3) {
      setFormError('Title must be at least 3 characters.')
      return
    }
    setFormError(null)
    try {
      await addMutation.mutateAsync({
        source_type: form.source_type,
        title,
        url: form.url?.trim() || null,
      })
      onClose()
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      const msg =
        typeof detail === 'object' && detail !== null
          ? (detail as { message?: string }).message
          : typeof detail === 'string'
          ? detail
          : null
      setFormError(msg ?? 'Failed to add item. Please try again.')
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-blue-200 bg-blue-50/40 px-4 py-4 space-y-3"
    >
      <p className="text-sm font-semibold text-gray-800">Add Faculty Resource</p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {/* Source type */}
        <div>
          <label className="block text-xs text-gray-500 mb-1">Source Type</label>
          <select
            value={form.source_type}
            onChange={(e) => setForm((f) => ({ ...f, source_type: e.target.value as MaterialSourceType }))}
            className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-2 text-sm text-gray-800 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
          >
            {ALL_SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>{SOURCE_LABELS[t]}</option>
            ))}
          </select>
        </div>

        {/* URL */}
        <div>
          <label className="block text-xs text-gray-500 mb-1">URL (optional)</label>
          <input
            type="url"
            value={form.url ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            placeholder="https://…"
            className="w-full rounded-lg border border-gray-200 px-2.5 py-2 text-sm text-gray-800 placeholder-gray-300 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
          />
        </div>
      </div>

      {/* Title */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">Title <span className="text-red-400">*</span></label>
        <input
          type="text"
          value={form.title}
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
          placeholder="Resource title…"
          maxLength={500}
          className="w-full rounded-lg border border-gray-200 px-2.5 py-2 text-sm text-gray-800 placeholder-gray-300 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
        />
      </div>

      {formError && (
        <p className="text-xs text-red-500">{formError}</p>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!form.title.trim() || addMutation.isPending}
        >
          {addMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Add Resource'}
        </Button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Pending item action state: track which itemId is being toggled/removed
// ---------------------------------------------------------------------------

function useItemActions(packageId: string) {
  const toggleMutation = useToggleRecommendation(packageId)
  const removeMutation = useRemoveItem(packageId)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)

  const toggle = async (item: PackageItem) => {
    setTogglingId(item.id)
    try {
      await toggleMutation.mutateAsync({ itemId: item.id, value: !item.faculty_recommended })
    } finally {
      setTogglingId(null)
    }
  }

  const remove = async (itemId: string) => {
    setRemovingId(itemId)
    try {
      await removeMutation.mutateAsync(itemId)
    } finally {
      setRemovingId(null)
    }
  }

  return { toggle, remove, togglingId, removingId }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function FacultyCuratePage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc       = useQueryClient()

  const packageId = id ?? ''
  const role      = localStorage.getItem('vidya_role') ?? ''
  const isDean    = role === 'DEAN'

  const { data: pkg, isLoading: pkgLoading, isError: pkgError } =
    useLearningPackage(packageId)

  const { data: items = [], isLoading: itemsLoading } =
    usePackageItems(packageId)

  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [addItemOpen, setAddItemOpen] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const jobQuery   = usePackageJob(activeJobId ?? '')
  const jobData    = jobQuery.data as JobStatus | undefined

  const curateM  = useTriggerCuration()
  const indexM   = useTriggerIndexing()
  const actions  = useItemActions(packageId)

  // ── Auto-poll package while CURATING ──────────────────────────────────────
  useEffect(() => {
    if (pkg?.status !== 'CURATING') return
    const t = setInterval(() => {
      qc.invalidateQueries({ queryKey: learningPackageKeys.detail(packageId) })
      qc.invalidateQueries({ queryKey: learningPackageKeys.items(packageId, false) })
    }, 5000)
    return () => clearInterval(t)
  }, [pkg?.status, packageId, qc])

  // ── Refresh package + items when active job finishes ─────────────────────
  useEffect(() => {
    if (!activeJobId) return
    const s = jobData?.status
    if (s !== 'SUCCESS' && s !== 'FAILED') return
    qc.invalidateQueries({ queryKey: learningPackageKeys.detail(packageId) })
    qc.invalidateQueries({ queryKey: learningPackageKeys.items(packageId, false) })
    const t = setTimeout(() => setActiveJobId(null), 4000)
    return () => clearTimeout(t)
  }, [activeJobId, jobData?.status, packageId, qc])

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleTriggerCuration = async () => {
    if (!pkg) return
    setActionError(null)
    try {
      const result = await curateM.mutateAsync({
        syllabus_id: pkg.syllabus_id,
        unit_number: pkg.unit_number,
      })
      setActiveJobId(result.job_id)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      const msg =
        typeof detail === 'object' && detail !== null
          ? (detail as { message?: string }).message
          : typeof detail === 'string'
          ? detail
          : null
      setActionError(msg ?? 'Failed to trigger curation.')
    }
  }

  const handleTriggerIndexing = async () => {
    setActionError(null)
    try {
      const result = await indexM.mutateAsync(packageId)
      setActiveJobId(result.job_id)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })
        ?.response?.data?.detail
      const msg =
        typeof detail === 'object' && detail !== null
          ? (detail as { message?: string }).message
          : typeof detail === 'string'
          ? detail
          : null
      setActionError(msg ?? 'Failed to trigger RAG indexing.')
    }
  }

  // ── Loading / error states ─────────────────────────────────────────────
  if (pkgLoading) {
    return (
      <div className="flex items-center justify-center py-24 gap-2 text-gray-400">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-sm">Loading package…</span>
      </div>
    )
  }

  if (pkgError || !pkg) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12">
        <div className="rounded-xl bg-red-50 border border-red-200 px-5 py-4 flex items-center gap-3 text-red-700">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <p className="text-sm font-medium">Package not found or not accessible.</p>
        </div>
        <Button variant="ghost" size="sm" className="mt-4" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Go back
        </Button>
      </div>
    )
  }

  const isCurating = pkg.status === 'CURATING'
  const isJobActive = Boolean(activeJobId) &&
    (jobData?.status === 'PENDING' || jobData?.status === 'RUNNING')
  const curateDisabled = isCurating || isJobActive || curateM.isPending
  const indexDisabled  = pkg.qdrant_indexed || pkg.status !== 'READY' || isJobActive || indexM.isPending

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-6">

      {/* ── Back ── */}
      <Button
        variant="ghost"
        size="sm"
        className="-mt-2 -ml-1"
        onClick={() => navigate(-1)}
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back
      </Button>

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">
              Unit {pkg.unit_number} — Faculty Curation
            </h1>
            <PackageStatusBadge status={pkg.status} />
            {pkg.qdrant_indexed && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-green-700 bg-green-50 border border-green-200 rounded-full px-2 py-0.5">
                <Database className="h-3 w-3" />
                RAG indexed
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">
            v{pkg.version}
            {' · '}
            {pkg.item_count} resource{pkg.item_count !== 1 ? 's' : ''}
            {' · '}
            <span className="font-mono">{pkg.syllabus_id.slice(0, 8)}…</span>
            {pkg.curated_at && (
              <> · Curated {new Date(pkg.curated_at).toLocaleDateString()}</>
            )}
          </p>
        </div>
      </div>

      {/* ── Pipeline stepper ── */}
      <PackageStepper status={pkg.status} />

      {/* ── Action bar ── */}
      {isDean ? (
        <div className="rounded-lg border border-blue-100 bg-blue-50 px-4 py-3 text-sm text-blue-700 flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          You have read-only access. Curation and indexing are managed by Faculty and Admin.
        </div>
      ) : (
        <div className="flex items-center gap-3 flex-wrap">
          <Button
            onClick={handleTriggerCuration}
            disabled={curateDisabled}
            className="gap-1.5"
          >
            {(curateM.isPending || isCurating) ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            {isCurating ? 'Curating…' : 'Trigger Curation'}
          </Button>

          <Button
            variant="outline"
            onClick={handleTriggerIndexing}
            disabled={indexDisabled}
            className="gap-1.5"
            title={
              pkg.qdrant_indexed ? 'Already indexed'
              : pkg.status !== 'READY' ? 'Trigger curation first'
              : undefined
            }
          >
            {indexM.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Database className="h-4 w-4" />
            )}
            Index for RAG
            {pkg.qdrant_indexed && (
              <CheckCircle2 className="h-3.5 w-3.5 text-green-500 ml-0.5" />
            )}
          </Button>

          {actionError && (
            <p className="text-xs text-red-500 flex items-center gap-1">
              <AlertTriangle className="h-3.5 w-3.5" />
              {actionError}
            </p>
          )}
        </div>
      )}

      {/* ── Job feedback ── */}
      {activeJobId && <JobBanner job={jobData} />}

      {/* ── Outdated notice ── */}
      {pkg.status === 'OUTDATED' && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3 text-sm text-orange-800 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          This package is outdated. Re-trigger curation to generate a fresh version.
        </div>
      )}

      {/* ── Items section ── */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-800">
            Resources
            <span className="ml-2 text-sm font-normal text-gray-400 tabular-nums">
              ({items.length})
            </span>
          </h2>
          {!isDean && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setAddItemOpen((v) => !v)}
            >
              <Plus className="h-4 w-4" />
              Add Faculty Resource
            </Button>
          )}
        </div>

        {/* Add item inline form */}
        {addItemOpen && !isDean && (
          <AddItemForm
            packageId={packageId}
            onClose={() => setAddItemOpen(false)}
          />
        )}

        {/* Items list */}
        {itemsLoading ? (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white">
            {[1, 2, 3].map((n) => (
              <div key={n} className="px-4 py-3 animate-pulse flex items-center gap-3">
                <div className="h-5 w-16 rounded-full bg-gray-200" />
                <div className="flex-1 h-4 rounded bg-gray-100" />
                <div className="h-4 w-8 rounded bg-gray-100" />
                <div className="h-5 w-5 rounded bg-gray-100" />
                <div className="h-5 w-5 rounded bg-gray-100" />
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="text-center py-14 rounded-xl border border-dashed border-gray-200">
            <Database className="h-9 w-9 mx-auto mb-3 text-gray-200" />
            <p className="text-sm text-gray-400">
              No resources yet. Trigger curation or add a faculty item.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {/* Column header */}
            <div className="hidden sm:flex items-center gap-3 px-4 py-2 bg-gray-50 text-[11px] font-semibold text-gray-400 uppercase tracking-wide">
              <span className="w-20 shrink-0">Source</span>
              <span className="flex-1">Title</span>
              <span className="w-8 text-right">Rel.</span>
              <span className="w-6 text-center">Fav</span>
              <span className="w-6" />
            </div>
            {items.map((item) => (
              <ItemCurateRow
                key={item.id}
                item={item}
                toggling={actions.togglingId === item.id}
                removing={actions.removingId === item.id}
                onToggle={isDean ? () => {} : () => actions.toggle(item)}
                onRemove={isDean ? () => {} : () => actions.remove(item.id)}
                readOnly={isDean}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
