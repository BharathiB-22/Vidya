// M09.8 Examination Analytics — reusable, dependency-free chart primitives.
//
// The project has no charting library; charts are hand-built with CSS bars and
// inline SVG (matching SessionStatisticsPage).  These primitives are generic so
// any future analytics dashboard can reuse them.
import type { ReactNode } from 'react'
import { BarChart2 } from 'lucide-react'

// ---------------------------------------------------------------------------
// StatCard — single KPI tile
// ---------------------------------------------------------------------------

export function StatCard({
  label, value, sub, icon: Icon, colorClass,
}: {
  label: string
  value: ReactNode
  sub?: string
  icon: typeof BarChart2
  colorClass: string
}) {
  return (
    <div className={`rounded-xl border px-4 py-4 space-y-1.5 ${colorClass}`}>
      <Icon className="h-4 w-4 opacity-70" />
      <p className="text-2xl font-bold">{value ?? '—'}</p>
      <p className="text-xs font-medium opacity-80">{label}</p>
      {sub && <p className="text-xs opacity-60">{sub}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// SectionCard — titled panel wrapper
// ---------------------------------------------------------------------------

export function SectionCard({
  title, subtitle, icon: Icon, action, children,
}: {
  title: string
  subtitle?: string
  icon?: typeof BarChart2
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="rounded-xl border border-gray-100 bg-white p-5 space-y-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="h-4 w-4 text-indigo-500" />}
          <div>
            <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
            {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
          </div>
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// EmptyState — for empty datasets (no error, just no data yet)
// ---------------------------------------------------------------------------

export function EmptyState({ message = 'No data available yet' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-gray-600 text-sm gap-2">
      <BarChart2 className="h-6 w-6 opacity-50" />
      {message}
    </div>
  )
}

// ---------------------------------------------------------------------------
// BarList — horizontal bar chart for ranked rows (subjects / batches / faculty)
// ---------------------------------------------------------------------------

export interface BarItem {
  label: string
  sublabel?: string
  value: number          // bar magnitude
  display?: string       // text to show on the right (defaults to value)
  tone?: 'indigo' | 'green' | 'red' | 'amber' | 'teal'
}

const TONE: Record<NonNullable<BarItem['tone']>, string> = {
  indigo: 'bg-indigo-400',
  green:  'bg-green-400',
  red:    'bg-red-300',
  amber:  'bg-amber-400',
  teal:   'bg-teal-400',
}

export function BarList({ items, max }: { items: BarItem[]; max?: number }) {
  if (items.length === 0) return <EmptyState />
  const maxVal = max ?? Math.max(...items.map(i => i.value), 1)
  return (
    <div className="space-y-2.5">
      {items.map((it, idx) => {
        const barPct = Math.max((it.value / maxVal) * 100, it.value > 0 ? 2 : 0)
        return (
          <div key={`${it.label}-${idx}`} className="flex items-center gap-3">
            <div className="w-32 shrink-0 truncate">
              <p className="text-xs font-medium text-gray-800 truncate">{it.label}</p>
              {it.sublabel && <p className="text-[10px] text-gray-600 truncate">{it.sublabel}</p>}
            </div>
            <div className="flex-1 h-6 bg-gray-100 rounded-md overflow-hidden">
              <div
                className={`h-full rounded-md transition-all ${TONE[it.tone ?? 'indigo']}`}
                style={{ width: `${barPct}%` }}
              />
            </div>
            <span className="w-16 text-right text-xs font-semibold text-gray-700 shrink-0">
              {it.display ?? it.value}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// GradeHistogram — vertical bars for the A+ … F grade distribution
// ---------------------------------------------------------------------------

const GRADE_COLOR: Record<string, string> = {
  'A+': 'bg-emerald-500',
  'A':  'bg-green-500',
  'B+': 'bg-lime-500',
  'B':  'bg-yellow-400',
  'C':  'bg-amber-400',
  'D':  'bg-orange-400',
  'F':  'bg-red-400',
}

export function GradeHistogram({
  buckets,
}: {
  buckets: { grade: string; count: number; pct_of_total: number }[]
}) {
  const total = buckets.reduce((a, b) => a + b.count, 0)
  if (total === 0) return <EmptyState message="No graded scripts yet" />
  const maxCount = Math.max(...buckets.map(b => b.count), 1)
  return (
    <div className="flex items-end justify-between gap-2 h-44 pt-2">
      {buckets.map(b => {
        const h = (b.count / maxCount) * 100
        return (
          <div key={b.grade} className="flex-1 flex flex-col items-center justify-end gap-1 h-full">
            <span className="text-[10px] font-medium text-gray-500">{b.count}</span>
            <div className="w-full flex items-end justify-center h-full">
              <div
                className={`w-full max-w-[2.5rem] rounded-t-md transition-all ${GRADE_COLOR[b.grade] ?? 'bg-gray-400'}`}
                style={{ height: `${Math.max(h, b.count > 0 ? 4 : 0)}%` }}
                title={`${b.count} scripts (${b.pct_of_total}%)`}
              />
            </div>
            <span className="text-xs font-semibold text-gray-700">{b.grade}</span>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PassFailBar — horizontal stacked pass/fail bar with legend
// ---------------------------------------------------------------------------

export function PassFailBar({ passCount, failCount }: { passCount: number; failCount: number }) {
  const total = passCount + failCount
  if (total === 0) return <EmptyState message="No results published yet" />
  const passPct = Math.round((passCount / total) * 100)
  const failPct = 100 - passPct
  return (
    <div className="space-y-3">
      <div className="flex h-8 rounded-full overflow-hidden gap-0.5">
        {passCount > 0 && (
          <div
            className="h-full bg-green-500 flex items-center justify-center text-white text-xs font-semibold"
            style={{ width: `${passPct}%` }}
          >
            {passPct >= 12 ? `${passPct}%` : ''}
          </div>
        )}
        {failCount > 0 && (
          <div
            className="h-full bg-red-400 flex items-center justify-center text-white text-xs font-semibold"
            style={{ width: `${failPct}%` }}
          >
            {failPct >= 12 ? `${failPct}%` : ''}
          </div>
        )}
      </div>
      <div className="flex justify-around text-sm">
        <div className="text-center">
          <p className="font-bold text-gray-800 text-lg">{passCount}</p>
          <p className="text-xs text-gray-500">Passed ({passPct}%)</p>
        </div>
        <div className="text-center">
          <p className="font-bold text-gray-800 text-lg">{failCount}</p>
          <p className="text-xs text-gray-500">Failed ({failPct}%)</p>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// DonutChart — true SVG donut (pie) for categorical segments
// ---------------------------------------------------------------------------

export interface DonutSegment {
  label: string
  value: number
  colorHex: string
}

export function DonutChart({ segments, centerLabel, centervalue }: {
  segments: DonutSegment[]
  centerLabel?: string
  centervalue?: string
}) {
  const total = segments.reduce((a, s) => a + s.value, 0)
  if (total === 0) return <EmptyState />

  const radius = 60
  const stroke = 22
  const circumference = 2 * Math.PI * radius
  let offset = 0

  return (
    <div className="flex items-center gap-6 flex-wrap">
      <svg width="160" height="160" viewBox="0 0 160 160" className="shrink-0">
        <g transform="translate(80,80) rotate(-90)">
          {segments.filter(s => s.value > 0).map((s, i) => {
            const frac = s.value / total
            const dash = frac * circumference
            const seg = (
              <circle
                key={i}
                r={radius}
                fill="none"
                stroke={s.colorHex}
                strokeWidth={stroke}
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeDashoffset={-offset}
              />
            )
            offset += dash
            return seg
          })}
        </g>
        <text x="80" y="74" textAnchor="middle" className="fill-gray-900 text-xl font-bold">
          {centervalue ?? total}
        </text>
        {centerLabel && (
          <text x="80" y="92" textAnchor="middle" className="fill-gray-400 text-[10px]">
            {centerLabel}
          </text>
        )}
      </svg>
      <div className="space-y-1.5">
        {segments.map((s, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: s.colorHex }} />
            <span className="text-gray-600">{s.label}</span>
            <span className="font-semibold text-gray-800">{s.value}</span>
            <span className="text-gray-600">({Math.round(s.value / total * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  )
}
