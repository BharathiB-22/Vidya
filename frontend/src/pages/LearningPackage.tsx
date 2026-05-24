/**
 * LearningPackage.tsx — Rich detail page for a Learning Package.
 *
 * Route: /learning-packages/:id
 *
 * Features:
 *   - Overview stats (resources, faculty picks, indexed count, version)
 *   - Content breakdown by source type
 *   - Source-type filter tabs (All / YouTube / arXiv / NPTEL / MIT OCW / Faculty)
 *   - Rich item cards: source badge, title, metadata, relevance, per-item indexed dot
 *   - Inline faculty curation: pin/unpin, remove, add custom resource (ADMIN/FACULTY)
 *   - Enriched RAG indexing status row with per-item count
 *   - Chat-style Q&A (NotebookQA) with pre-indexing guidance
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  ExternalLink,
  Download,
  Settings2,
  Star,
  Loader2,
  AlertTriangle,
  BookOpen,
  Video,
  FileText,
  GraduationCap,
  Library,
  Database,
  CheckCircle2,
  Plus,
  Trash2,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PackageStatusBadge } from '@/components/learningPackage/PackageStatusBadge'
import { NotebookQA } from '@/components/NotebookQA'
import {
  useLearningPackage,
  usePackageItems,
  useAddFacultyItem,
  useRemoveItem,
  useToggleRecommendation,
} from '@/hooks/learningPackage'
import type {
  FacultyAddItemPayload,
  LearningPackage,
  MaterialSourceType,
  PackageItem,
} from '@/types/learningPackage'

// ---------------------------------------------------------------------------
// Source configuration
// ---------------------------------------------------------------------------

const SOURCE_CONFIG: Record<
  MaterialSourceType,
  { label: string; icon: React.ElementType; variant: 'default' | 'warning' | 'info' | 'success' | 'destructive' }
> = {
  YOUTUBE:      { label: 'YouTube',      icon: Video,         variant: 'destructive' },
  ARXIV:        { label: 'arXiv',        icon: FileText,      variant: 'info'        },
  NPTEL:        { label: 'NPTEL',        icon: GraduationCap, variant: 'warning'     },
  MIT_OCW:      { label: 'MIT OCW',      icon: Library,       variant: 'success'     },
  FACULTY_NOTE: { label: 'Faculty Note', icon: BookOpen,      variant: 'default'     },
}

const ALL_SOURCE_TYPES: MaterialSourceType[] = [
  'YOUTUBE', 'ARXIV', 'NPTEL', 'MIT_OCW', 'FACULTY_NOTE',
]

type SourceFilter = MaterialSourceType | 'ALL'

const FILTER_TABS: Array<{ key: SourceFilter; label: string }> = [
  { key: 'ALL',          label: 'All'     },
  { key: 'YOUTUBE',      label: 'YouTube' },
  { key: 'ARXIV',        label: 'arXiv'   },
  { key: 'NPTEL',        label: 'NPTEL'   },
  { key: 'MIT_OCW',      label: 'MIT OCW' },
  { key: 'FACULTY_NOTE', label: 'Faculty' },
]

// ---------------------------------------------------------------------------
// Item actions hook
// ---------------------------------------------------------------------------

function useItemActions(packageId: string) {
  const toggleMutation = useToggleRecommendation(packageId)
  const removeMutation  = useRemoveItem(packageId)
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
// Sub-components
// ---------------------------------------------------------------------------

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-100 p-4 animate-pulse space-y-2">
      <div className="flex items-center gap-2">
        <div className="h-5 w-16 rounded-full bg-gray-200" />
        <div className="h-4 w-48 rounded bg-gray-200" />
      </div>
      <div className="h-3 w-full rounded bg-gray-100" />
      <div className="h-2.5 w-32 rounded-full bg-gray-100" />
    </div>
  )
}

function RelevanceBar({ score }: { score: number | null }) {
  if (score === null) return null
  const pct = Math.round(score * 100)
  return (
    <div className="flex items-center gap-2 mt-1.5">
      <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden max-w-[120px]">
        <div
          className="h-full rounded-full bg-blue-400 transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 tabular-nums">{pct}% match</span>
    </div>
  )
}

function SourceBadge({ sourceType }: { sourceType: MaterialSourceType }) {
  const cfg = SOURCE_CONFIG[sourceType]
  const Icon = cfg.icon
  return (
    <Badge variant={cfg.variant} className="gap-1 shrink-0">
      <Icon className="h-3 w-3" />
      {cfg.label}
    </Badge>
  )
}

function ItemMetaLine({ item }: { item: PackageItem }) {
  const meta = item.metadata
  const parts: string[] = []
  if (item.source_type === 'YOUTUBE' && meta.duration_seconds) {
    const m = Math.floor(meta.duration_seconds / 60)
    const s = meta.duration_seconds % 60
    parts.push(`${m}:${String(s).padStart(2, '0')} min`)
  }
  if (meta.authors && meta.authors.length > 0) {
    parts.push(
      meta.authors.slice(0, 2).join(', ') +
      (meta.authors.length > 2 ? ' et al.' : ''),
    )
  }
  if (meta.publish_date) parts.push(meta.publish_date.slice(0, 4))
  if (meta.abstract_snippet) {
    parts.push(
      meta.abstract_snippet.slice(0, 120) +
      (meta.abstract_snippet.length > 120 ? '…' : ''),
    )
  }
  if (parts.length === 0) return null
  return (
    <p className="text-xs text-gray-400 mt-1 line-clamp-2">{parts.join(' · ')}</p>
  )
}

function ItemCard({
  item,
  canModifyItem,
  onStar,
  onRemove,
  isStar,
  isRemove,
}: {
  item:          PackageItem
  canModifyItem: boolean
  onStar:        () => void
  onRemove:      () => void
  isStar:        boolean
  isRemove:      boolean
}) {
  const [confirmRemove, setConfirmRemove] = useState(false)

  function handleRemoveClick() {
    if (confirmRemove) {
      onRemove()
      setConfirmRemove(false)
    } else {
      setConfirmRemove(true)
      setTimeout(() => setConfirmRemove(false), 3000)
    }
  }

  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 hover:border-gray-200 transition-colors">
      <div className="flex items-start justify-between gap-3">
        {/* Left: content */}
        <div className="flex-1 min-w-0">
          {/* Badge row */}
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <SourceBadge sourceType={item.source_type} />
            {item.faculty_recommended && (
              <Badge variant="warning" className="gap-1">
                <Star className="h-3 w-3 fill-current" />
                Faculty Pick
              </Badge>
            )}
            {item.qdrant_indexed && (
              <span className="inline-flex items-center gap-1 text-[10px] text-green-600 bg-green-50 border border-green-100 rounded-full px-1.5 py-0.5">
                <CheckCircle2 className="h-2.5 w-2.5" />
                Indexed
              </span>
            )}
          </div>

          {/* Title */}
          {item.url ? (
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-gray-900 hover:text-blue-700 hover:underline underline-offset-2 flex items-start gap-1 group"
            >
              <span className="line-clamp-2">{item.title}</span>
              <ExternalLink className="h-3.5 w-3.5 mt-0.5 shrink-0 text-gray-300 group-hover:text-blue-500 transition-colors" />
            </a>
          ) : (
            <p className="text-sm font-medium text-gray-900 line-clamp-2">{item.title}</p>
          )}

          <ItemMetaLine item={item} />
          <RelevanceBar score={item.relevance_score} />
        </div>

        {/* Right: thumbnail + actions */}
        <div className="flex flex-col items-end gap-2 shrink-0">
          {item.source_type === 'YOUTUBE' && item.metadata.thumbnail_url && (
            <img
              src={item.metadata.thumbnail_url}
              alt=""
              className="w-20 h-14 rounded-md object-cover"
            />
          )}

          {canModifyItem && (
            <div className="flex items-center gap-0.5 mt-auto">
              {/* Star / Faculty Pick toggle */}
              <button
                type="button"
                title={item.faculty_recommended ? 'Remove Faculty Pick' : 'Mark as Faculty Pick'}
                disabled={isStar}
                onClick={onStar}
                className={`rounded-md p-1.5 transition-colors disabled:opacity-50 ${
                  item.faculty_recommended
                    ? 'text-amber-500 hover:text-amber-600 bg-amber-50'
                    : 'text-gray-300 hover:text-amber-400'
                }`}
              >
                {isStar
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Star className={`h-3.5 w-3.5 ${item.faculty_recommended ? 'fill-current' : ''}`} />
                }
              </button>

              {/* Remove */}
              <button
                type="button"
                title={confirmRemove ? 'Click again to confirm removal' : 'Remove resource'}
                disabled={isRemove}
                onClick={handleRemoveClick}
                className={`rounded-md p-1.5 transition-colors disabled:opacity-50 ${
                  confirmRemove
                    ? 'text-red-600 bg-red-50'
                    : 'text-gray-300 hover:text-red-400'
                }`}
              >
                {isRemove
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Trash2 className="h-3.5 w-3.5" />
                }
              </button>
            </div>
          )}
        </div>
      </div>
      {confirmRemove && (
        <p className="mt-2 text-[11px] text-red-500">Click remove again to confirm.</p>
      )}
    </div>
  )
}

// Overview stats bar
function OverviewStats({
  pkg,
  items,
}: {
  pkg:   LearningPackage
  items: PackageItem[]
}) {
  const facultyPicks  = items.filter((i) => i.faculty_recommended).length
  const indexedCount  = items.filter((i) => i.qdrant_indexed).length

  const sourceCounts = ALL_SOURCE_TYPES
    .map((t) => ({ type: t, count: items.filter((i) => i.source_type === t).length }))
    .filter((e) => e.count > 0)

  return (
    <div className="space-y-3">
      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
          <p className="text-xl font-bold text-gray-800">{items.length}</p>
          <p className="text-xs text-gray-500 mt-0.5">Resources</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
          <p className="text-xl font-bold text-amber-600">{facultyPicks}</p>
          <p className="text-xs text-gray-500 mt-0.5">Faculty Picks</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
          <p className={`text-xl font-bold ${indexedCount === items.length && items.length > 0 ? 'text-green-700' : 'text-gray-800'}`}>
            {indexedCount}<span className="text-sm font-normal text-gray-400">/{items.length}</span>
          </p>
          <p className="text-xs text-gray-500 mt-0.5">RAG Indexed</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
          <p className="text-xl font-bold text-gray-800">v{pkg.version}</p>
          <p className="text-xs text-gray-500 mt-0.5">
            {pkg.curated_at
              ? `Curated ${new Date(pkg.curated_at).toLocaleDateString()}`
              : `Created ${new Date(pkg.created_at).toLocaleDateString()}`}
          </p>
        </div>
      </div>

      {/* Content breakdown chips */}
      {sourceCounts.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-400 font-medium">Sources:</span>
          {sourceCounts.map(({ type, count }) => {
            const cfg  = SOURCE_CONFIG[type]
            const Icon = cfg.icon
            return (
              <span
                key={type}
                className="inline-flex items-center gap-1 text-xs text-gray-600 bg-gray-100 rounded-full px-2.5 py-0.5"
              >
                <Icon className="h-3 w-3 text-gray-400" />
                {cfg.label} ({count})
              </span>
            )
          })}
          {pkg.ai_model && (
            <span className="text-xs text-gray-400 font-mono ml-auto">
              {pkg.ai_model}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// Enriched RAG indexing status panel
function RagStatusPanel({
  pkg,
  items,
  canCurate,
  onGoToCurate,
}: {
  pkg:         LearningPackage
  items:       PackageItem[]
  canCurate:   boolean
  onGoToCurate:() => void
}) {
  const indexedCount = items.filter((i) => i.qdrant_indexed).length
  const total        = items.length
  const isIndexed    = pkg.qdrant_indexed

  return (
    <div className={`rounded-lg border px-4 py-3 flex items-center gap-3 flex-wrap text-sm ${
      isIndexed
        ? 'border-green-200 bg-green-50'
        : 'border-amber-200 bg-amber-50'
    }`}>
      <div className={`flex items-center gap-2 font-medium ${isIndexed ? 'text-green-700' : 'text-amber-700'}`}>
        {isIndexed
          ? <CheckCircle2 className="h-4 w-4 shrink-0" />
          : <Database className="h-4 w-4 shrink-0" />
        }
        {isIndexed ? 'RAG Indexed — Q&A ready' : 'RAG Indexing Pending'}
      </div>

      <span className={`text-xs px-2 py-0.5 rounded-full border ${
        isIndexed
          ? 'bg-green-100 border-green-200 text-green-700'
          : 'bg-amber-100 border-amber-200 text-amber-700'
      }`}>
        {indexedCount} of {total} resources indexed
      </span>

      {!isIndexed && canCurate && (
        <button
          type="button"
          onClick={onGoToCurate}
          className="ml-auto text-xs underline underline-offset-2 text-amber-700 hover:text-amber-800"
        >
          Go to Faculty Curation to trigger indexing →
        </button>
      )}
    </div>
  )
}

// Inline "Add Faculty Resource" form
function AddResourceInline({
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const title = form.title.trim()
    if (title.length < 3) { setFormError('Title must be at least 3 characters.'); return }
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
      setFormError(msg ?? 'Failed to add item — please try again.')
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-blue-200 bg-blue-50/40 px-4 py-4 space-y-3"
    >
      <p className="text-sm font-semibold text-gray-800">Add Faculty Resource</p>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Source Type</label>
          <select
            value={form.source_type}
            onChange={(e) =>
              setForm((f) => ({ ...f, source_type: e.target.value as MaterialSourceType }))
            }
            className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-2 text-sm text-gray-800 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
          >
            {ALL_SOURCE_TYPES.map((t) => (
              <option key={t} value={t}>{SOURCE_CONFIG[t].label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">URL (optional)</label>
          <input
            type="url"
            value={form.url ?? ''}
            onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
            placeholder="https://…"
            className="w-full rounded-lg border border-gray-200 px-2.5 py-2 text-sm placeholder-gray-300 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">
          Title <span className="text-red-400">*</span>
        </label>
        <input
          type="text"
          value={form.title}
          onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
          placeholder="Resource title…"
          maxLength={500}
          className="w-full rounded-lg border border-gray-200 px-2.5 py-2 text-sm placeholder-gray-300 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-100"
        />
      </div>

      {formError && <p className="text-xs text-red-500">{formError}</p>}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button
          type="submit"
          size="sm"
          disabled={!form.title.trim() || addMutation.isPending}
        >
          {addMutation.isPending
            ? <Loader2 className="h-4 w-4 animate-spin" />
            : 'Add Resource'
          }
        </Button>
      </div>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const FACULTY_ROLES = ['ADMIN', 'FACULTY']

export default function LearningPackagePage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()

  const packageId  = id ?? ''
  const role       = localStorage.getItem('vidya_role') ?? ''
  const canCurate  = FACULTY_ROLES.includes(role)

  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('ALL')
  const [showAddForm,  setShowAddForm]  = useState(false)

  // Package is mutable when PENDING or READY (not CURATING or OUTDATED)
  const isMutable = (s: string) => s === 'PENDING' || s === 'READY'

  const { data: pkg, isLoading: pkgLoading, isError: pkgError } =
    useLearningPackage(packageId)

  const { data: allItems = [], isLoading: itemsLoading } =
    usePackageItems(packageId)

  // Always call hooks — show UI conditionally
  const itemActions = useItemActions(packageId)

  const filteredItems: PackageItem[] =
    sourceFilter === 'ALL'
      ? allItems
      : allItems.filter((it) => it.source_type === sourceFilter)

  const countBySource = (key: SourceFilter) =>
    key === 'ALL'
      ? allItems.length
      : allItems.filter((it) => it.source_type === key).length

  // ── Loading / error states ────────────────────────────────────────────────

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
          <div>
            <p className="font-medium text-sm">Package not found</p>
            <p className="text-xs mt-0.5">This learning package does not exist or is not accessible.</p>
          </div>
        </div>
        <Button variant="ghost" size="sm" className="mt-4" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-4 w-4 mr-1" />
          Go back
        </Button>
      </div>
    )
  }

  const curatePath = `/learning-packages/${packageId}/curate`

  // ── Render ────────────────────────────────────────────────────────────────

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
              Unit {pkg.unit_number} — Learning Package
            </h1>
            <PackageStatusBadge status={pkg.status} />
          </div>
          <p className="text-sm text-gray-500 mt-1 font-mono">
            {pkg.syllabus_id.slice(0, 8)}… · Unit {pkg.unit_number} · v{pkg.version}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0 flex-wrap">
          {canCurate && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => navigate(curatePath)}
            >
              <Settings2 className="h-4 w-4" />
              Faculty Curation
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled
            title="PDF export is not yet available"
            className="gap-1.5 text-gray-400"
          >
            <Download className="h-4 w-4" />
            Export PDF
            <span className="text-[10px]">(soon)</span>
          </Button>
        </div>
      </div>

      {/* ── Overview stats ── */}
      {!itemsLoading && (
        <OverviewStats pkg={pkg} items={allItems} />
      )}

      {/* ── Curation status notice ── */}
      {pkg.status !== 'READY' && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {pkg.status === 'CURATING'
            ? 'AI curation is in progress. Check back shortly.'
            : pkg.status === 'OUTDATED'
            ? 'This package is outdated. Re-trigger curation from Faculty Curation.'
            : 'This package is pending curation.'}
          {canCurate && pkg.status !== 'CURATING' && (
            <button
              type="button"
              className="ml-auto underline underline-offset-2 text-yellow-700 hover:text-yellow-800 text-xs shrink-0"
              onClick={() => navigate(curatePath)}
            >
              Open Curation →
            </button>
          )}
        </div>
      )}

      {/* ── RAG indexing status row ── */}
      {!itemsLoading && (
        <RagStatusPanel
          pkg={pkg}
          items={allItems}
          canCurate={canCurate}
          onGoToCurate={() => navigate(curatePath)}
        />
      )}

      {/* ── Source filter tabs ── */}
      <div className="flex gap-2 flex-wrap border-b border-gray-100 pb-1">
        {FILTER_TABS.map((tab) => {
          const count = countBySource(tab.key)
          if (tab.key !== 'ALL' && count === 0) return null
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setSourceFilter(tab.key)}
              className={`px-3 py-1.5 rounded-t-lg text-sm font-medium transition-colors border-b-2 -mb-px ${
                sourceFilter === tab.key
                  ? 'text-gray-900 border-gray-900 bg-white'
                  : 'text-gray-500 border-transparent hover:text-gray-700'
              }`}
            >
              {tab.label}
              {count > 0 && (
                <span className="ml-1.5 text-xs tabular-nums text-gray-400">{count}</span>
              )}
            </button>
          )
        })}
      </div>

      {/* ── Resource list ── */}
      <div className="space-y-3">
        {/* List header row */}
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-gray-400 font-medium">
            {filteredItems.length} resource{filteredItems.length !== 1 ? 's' : ''}
            {sourceFilter !== 'ALL' && ` · ${SOURCE_CONFIG[sourceFilter as MaterialSourceType]?.label ?? sourceFilter} only`}
          </p>
          {canCurate && isMutable(pkg.status) && (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => setShowAddForm((v) => !v)}
            >
              <Plus className="h-4 w-4" />
              Add Resource
            </Button>
          )}
        </div>

        {/* Inline add form */}
        {showAddForm && canCurate && isMutable(pkg.status) && (
          <AddResourceInline
            packageId={packageId}
            onClose={() => setShowAddForm(false)}
          />
        )}

        {/* Items */}
        {itemsLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((n) => <SkeletonCard key={n} />)}
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
            <BookOpen className="h-10 w-10 mx-auto mb-3 text-gray-200" />
            <p className="text-sm text-gray-400">
              {sourceFilter === 'ALL'
                ? 'No learning materials in this package yet.'
                : `No ${SOURCE_CONFIG[sourceFilter as MaterialSourceType]?.label ?? sourceFilter} resources.`}
            </p>
            {sourceFilter !== 'ALL' && (
              <button
                type="button"
                onClick={() => setSourceFilter('ALL')}
                className="mt-3 text-xs text-blue-600 underline underline-offset-2"
              >
                Show all sources
              </button>
            )}
            {canCurate && sourceFilter === 'ALL' && (
              <div className="mt-4 flex flex-col items-center gap-2">
                <p className="text-xs text-gray-400">
                  Trigger AI curation or add a resource manually.
                </p>
                <Button size="sm" variant="outline" onClick={() => navigate(curatePath)}>
                  <Settings2 className="h-3.5 w-3.5 mr-1.5" />
                  Open Faculty Curation
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {filteredItems.map((item) => (
              <ItemCard
                key={item.id}
                item={item}
                canModifyItem={canCurate && pkg.status === 'READY'}
                onStar={() => itemActions.toggle(item)}
                onRemove={() => itemActions.remove(item.id)}
                isStar={itemActions.togglingId === item.id}
                isRemove={itemActions.removingId === item.id}
              />
            ))}
          </div>
        )}
      </div>

      {/* ── Q&A section ── */}
      <div className="pt-2">
        <NotebookQA
          packageId={packageId}
          qdrantIndexed={pkg.qdrant_indexed}
        />
        {!pkg.qdrant_indexed && canCurate && (
          <p className="mt-2 text-xs text-center text-gray-400">
            Q&A requires RAG indexing.{' '}
            <button
              type="button"
              className="text-blue-600 underline underline-offset-2"
              onClick={() => navigate(curatePath)}
            >
              Trigger indexing in Faculty Curation
            </button>
            .
          </p>
        )}
      </div>
    </div>
  )
}
