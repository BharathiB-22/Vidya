/**
 * LearningPackage.tsx — Student-facing package detail page (STEP-14).
 *
 * Route: /learning-packages/:id
 *
 * Features:
 *   - Package header: unit, version, status, item count, curated date
 *   - Source-type filter tabs (All / YouTube / arXiv / NPTEL / MIT OCW / Faculty)
 *   - Item cards: title link, source badge, Faculty Recommended badge,
 *     relevance bar, metadata (duration / authors / abstract snippet)
 *   - Offline PDF download placeholder button (export not implemented yet)
 *   - Responsive; follows M03 CourseKitDetailPage patterns
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  ExternalLink,
  Download,
  Star,
  Loader2,
  AlertTriangle,
  BookOpen,
  Video,
  FileText,
  GraduationCap,
  Library,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PackageStatusBadge } from '@/components/learningPackage/PackageStatusBadge'
import { useLearningPackage, usePackageItems } from '@/hooks/learningPackage'
import type { MaterialSourceType, PackageItem } from '@/types/learningPackage'

// ---------------------------------------------------------------------------
// Source type helpers
// ---------------------------------------------------------------------------

const SOURCE_CONFIG: Record<
  MaterialSourceType,
  {
    label:   string
    icon:    React.ElementType
    variant: 'default' | 'warning' | 'info' | 'success' | 'destructive'
  }
> = {
  YOUTUBE:      { label: 'YouTube',    icon: Video,       variant: 'destructive' },
  ARXIV:        { label: 'arXiv',      icon: FileText,    variant: 'info'        },
  NPTEL:        { label: 'NPTEL',      icon: GraduationCap, variant: 'warning'  },
  MIT_OCW:      { label: 'MIT OCW',    icon: Library,     variant: 'success'     },
  FACULTY_NOTE: { label: 'Faculty',    icon: BookOpen,    variant: 'default'     },
}

type SourceFilter = MaterialSourceType | 'ALL'

const FILTER_TABS: Array<{ key: SourceFilter; label: string }> = [
  { key: 'ALL',          label: 'All'       },
  { key: 'YOUTUBE',      label: 'YouTube'   },
  { key: 'ARXIV',        label: 'arXiv'     },
  { key: 'NPTEL',        label: 'NPTEL'     },
  { key: 'MIT_OCW',      label: 'MIT OCW'   },
  { key: 'FACULTY_NOTE', label: 'Faculty'   },
]

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
      <span className="text-xs text-gray-400 tabular-nums">{pct}%</span>
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
    parts.push(meta.authors.slice(0, 2).join(', ') + (meta.authors.length > 2 ? ' et al.' : ''))
  }
  if (meta.publish_date) {
    parts.push(meta.publish_date.slice(0, 4))
  }
  if (meta.abstract_snippet) {
    parts.push(meta.abstract_snippet.slice(0, 100) + (meta.abstract_snippet.length > 100 ? '…' : ''))
  }

  if (parts.length === 0) return null
  return (
    <p className="text-xs text-gray-400 mt-1 line-clamp-2">
      {parts.join(' · ')}
    </p>
  )
}

function ItemCard({ item }: { item: PackageItem }) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-4 hover:border-gray-200 transition-colors">
      {/* Title row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <SourceBadge sourceType={item.source_type} />
            {item.faculty_recommended && (
              <Badge variant="warning" className="gap-1">
                <Star className="h-3 w-3 fill-current" />
                Faculty Pick
              </Badge>
            )}
          </div>

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

        {/* Thumbnail for YouTube */}
        {item.source_type === 'YOUTUBE' && item.metadata.thumbnail_url && (
          <img
            src={item.metadata.thumbnail_url}
            alt=""
            className="w-20 h-14 rounded-md object-cover shrink-0"
          />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function LearningPackagePage() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('ALL')

  const packageId = id ?? ''

  const { data: pkg, isLoading: pkgLoading, isError: pkgError } =
    useLearningPackage(packageId)

  const { data: allItems = [], isLoading: itemsLoading } =
    usePackageItems(packageId)

  const filteredItems: PackageItem[] =
    sourceFilter === 'ALL'
      ? allItems
      : allItems.filter((it) => it.source_type === sourceFilter)

  // Count items by source type for tab badges
  const countBySource = (key: SourceFilter) =>
    key === 'ALL' ? allItems.length : allItems.filter((it) => it.source_type === key).length

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

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
              Unit {pkg.unit_number} Learning Package
            </h1>
            <PackageStatusBadge status={pkg.status} />
          </div>
          <div className="flex items-center gap-3 mt-1 text-sm text-gray-500 flex-wrap">
            <span>v{pkg.version}</span>
            <span className="text-gray-200">·</span>
            <span>{pkg.item_count} resource{pkg.item_count !== 1 ? 's' : ''}</span>
            {pkg.curated_at && (
              <>
                <span className="text-gray-200">·</span>
                <span>Curated {new Date(pkg.curated_at).toLocaleDateString()}</span>
              </>
            )}
          </div>
        </div>

        {/* ── PDF download placeholder ── */}
        <Button
          variant="outline"
          size="sm"
          disabled
          title="PDF export is not yet available for this module"
          className="shrink-0 gap-1.5"
        >
          <Download className="h-4 w-4" />
          Download PDF
          <span className="ml-1 text-[10px] font-normal text-gray-400">(coming soon)</span>
        </Button>
      </div>

      {/* ── Non-ready notice ── */}
      {pkg.status !== 'READY' && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 text-sm text-yellow-800 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {pkg.status === 'CURATING'
            ? 'AI curation is in progress. Check back shortly.'
            : pkg.status === 'OUTDATED'
            ? 'This package is outdated. A newer version may be available.'
            : 'This package is pending curation.'}
        </div>
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
                <span className="ml-1.5 text-xs tabular-nums text-gray-400">
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {/* ── Items ── */}
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
              : `No ${SOURCE_CONFIG[sourceFilter as MaterialSourceType]?.label ?? sourceFilter} resources in this package.`
            }
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
        </div>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </div>
      )}

      {/* ── Footer count ── */}
      {!itemsLoading && filteredItems.length > 0 && (
        <p className="text-xs text-gray-400 text-center pb-4">
          {filteredItems.length} resource{filteredItems.length !== 1 ? 's' : ''} shown
          {sourceFilter !== 'ALL' && ` · ${SOURCE_CONFIG[sourceFilter as MaterialSourceType]?.label ?? sourceFilter} only`}
        </p>
      )}
    </div>
  )
}
