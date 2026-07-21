import { useMemo, useState, type ComponentType, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  CalendarCheck, CheckCircle2, Clock, Download, FileSpreadsheet, ListChecks,
  Lock, Percent, Plus, Printer, Search, Users,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { sisApi } from '@/lib/api/sis'
import type { FacultyDayClass } from '@/lib/api/sis'
import { ExtraClassDialog } from './ExtraClassDialog'

const DOW = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

// ── date helpers (all local-time; no UTC drift) ─────────────────────────────
function toISO(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function todayISO(): string { return toISO(new Date()) }
function shiftISO(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  return toISO(new Date(y, m - 1, d + days))
}
function prettyDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d)
  return `${DOW[(date.getDay() + 6) % 7]}, ${d} ${MONTHS[m - 1]} ${y}`
}
/** Compact date label for the table: Today / Yesterday / "13 Jul 2026". */
function dateLabel(iso: string): string {
  if (iso === todayISO()) return 'Today'
  if (iso === shiftISO(todayISO(), -1)) return 'Yesterday'
  const [y, m, d] = iso.split('-').map(Number)
  return `${d} ${MONTHS[m - 1].slice(0, 3)} ${y}`
}
function fmtTime(t: string | null): string {
  if (!t) return ''
  const [h, m] = t.split(':')
  return `${Number(h)}:${m}`
}
function timeRange(c: FacultyDayClass): string {
  if (c.start_time && c.end_time) return `${fmtTime(c.start_time)}–${fmtTime(c.end_time)}`
  return c.period_label ?? `Period ${c.period_number}`
}
function sectionLabel(c: FacultyDayClass): string {
  if (c.is_elective) return 'All'
  return c.section_name ?? '—'
}

// ── view model ──────────────────────────────────────────────────────────────
type Filter = 'today' | 'yesterday' | 'last7' | 'date'

interface Row {
  date:     string
  editable: boolean          // does this row's DATE fall within the edit window?
  c:        FacultyDayClass
}

const HEADERS = ['Date', 'Time', 'Course', 'Section', 'Status', 'Present', 'Absent', 'Total']

function rowCells(r: Row): string[] {
  const c = r.c
  const taken = c.is_taken
  const present = taken ? String(c.present_count ?? 0) : ''
  const total   = taken ? String(c.total_marked ?? 0) : String(c.student_count)
  const absent  = taken ? String((c.total_marked ?? 0) - (c.present_count ?? 0)) : ''
  return [
    dateLabel(r.date), timeRange(c), `${c.course_code} ${c.course_title}`,
    sectionLabel(c), taken ? 'Completed' : 'Pending', present, absent, total,
  ]
}

// ── export helpers (frontend-only; existing data, no backend call) ──────────
function csvCell(v: string): string {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v
}
function escapeHtml(s: string): string {
  return s.replace(/[&<>]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]!))
}
function download(content: string, mime: string, filename: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}
function htmlTable(rows: Row[]): string {
  const head = `<tr>${HEADERS.map(h => `<th>${h}</th>`).join('')}</tr>`
  const body = rows.map(r => `<tr>${rowCells(r).map(c => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')
  return `<table><thead>${head}</thead><tbody>${body}</tbody></table>`
}

/**
 * Faculty Attendance — single-screen ERP dashboard.
 *
 * Everything the faculty needs is here: summary KPIs, quick date filters
 * (Today / Yesterday / Last 7 Days) plus a date picker, and one professional
 * table listing every scheduled class with status, counts and the correct
 * action (Take / Edit / View). Multi-day views are assembled client-side from
 * the same per-day endpoint — no backend, API, permission or workflow change.
 * The edit window is enforced by the backend; here it only decides Edit vs View.
 */
export default function FacultyAttendanceDashboard() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('today')
  const [pickedDate, setPickedDate] = useState(todayISO())
  const [search, setSearch] = useState('')
  const [extraOpen, setExtraOpen] = useState(false)

  // The set of dates this view needs, newest first.
  const dates = useMemo<string[]>(() => {
    if (filter === 'today') return [todayISO()]
    if (filter === 'yesterday') return [shiftISO(todayISO(), -1)]
    if (filter === 'date') return [pickedDate]
    return Array.from({ length: 7 }, (_, i) => shiftISO(todayISO(), -i)) // last7
  }, [filter, pickedDate])

  // One request per date (deduped/cached by React Query); merged into rows.
  const { data, isLoading, isError } = useQuery({
    queryKey: ['faculty-attendance', dates],
    queryFn: async (): Promise<Row[]> => {
      const days = await Promise.all(
        dates.map(async (d) => {
          const day = await sisApi.getFacultyToday(d)
          return (day.today ?? []).map((c) => ({ date: d, editable: day.editable ?? true, c }))
        })
      )
      return days.flat()
    },
  })

  const rows = data ?? []

  // KPIs summarise the whole loaded range (stable; unaffected by the search box).
  const kpi = useMemo(() => {
    const completed = rows.filter(r => r.c.is_taken)
    const pending   = rows.filter(r => !r.c.is_taken)
    const totMarked = completed.reduce((s, r) => s + (r.c.total_marked ?? 0), 0)
    const totPresent = completed.reduce((s, r) => s + (r.c.present_count ?? 0), 0)
    return {
      total: rows.length,
      completed: completed.length,
      pending: pending.length,
      avg: totMarked > 0 ? Math.round((totPresent / totMarked) * 100) : null,
    }
  }, [rows])

  // Search narrows only the table (course code/title or section).
  const visibleRows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const filtered = !q ? rows : rows.filter(r => {
      const c = r.c
      return (
        c.course_code.toLowerCase().includes(q) ||
        c.course_title.toLowerCase().includes(q) ||
        sectionLabel(c).toLowerCase().includes(q)
      )
    })
    // Newest date first, then by period within a day.
    return [...filtered].sort((a, b) =>
      a.date === b.date ? a.c.period_number - b.c.period_number : (a.date < b.date ? 1 : -1)
    )
  }, [rows, search])

  const countLabel =
    filter === 'today' ? "Today's Classes"
    : filter === 'yesterday' ? "Yesterday's Classes"
    : filter === 'last7' ? 'Classes (7 days)'
    : 'Classes'

  const rangeLabel =
    filter === 'today' ? `Today · ${prettyDate(todayISO())}`
    : filter === 'yesterday' ? `Yesterday · ${prettyDate(shiftISO(todayISO(), -1))}`
    : filter === 'last7' ? `Last 7 days · ${dateLabel(shiftISO(todayISO(), -6))} – Today`
    : prettyDate(pickedDate)

  function openAttendance(r: Row) {
    const c = r.c
    const p = new URLSearchParams({
      course_id: c.course_id,
      semester_id: c.semester_id,
      date: r.date,
      title: `${c.course_code} ${c.course_title}`,
      where: c.is_elective ? 'Combined class' : (c.section_name ? `Section ${c.section_name}` : ''),
      when: timeRange(c),
    })
    if (c.section_id) p.set('section_id', c.section_id)
    if (c.period_number != null) p.set('period', String(c.period_number))
    if (c.session_id) p.set('session_id', c.session_id)
    navigate(`/sis/attendance/take?${p.toString()}`)
  }

  function exportCsv() {
    const csv = [HEADERS, ...visibleRows.map(rowCells)].map(r => r.map(csvCell).join(',')).join('\n')
    download(csv, 'text/csv;charset=utf-8;', `attendance-${todayISO()}.csv`)
  }
  function exportExcel() {
    const html = `<html><head><meta charset="utf-8"></head><body>${htmlTable(visibleRows)}</body></html>`
    download(html, 'application/vnd.ms-excel', `attendance-${todayISO()}.xls`)
  }
  function printTable() {
    const w = window.open('', '_blank', 'width=980,height=720')
    if (!w) return
    w.document.write(
      `<html><head><title>Attendance — ${escapeHtml(rangeLabel)}</title>` +
      `<style>body{font-family:system-ui,sans-serif;padding:24px;color:#111}` +
      `h2{margin:0 0 4px}p{margin:0 0 16px;color:#666;font-size:13px}` +
      `table{border-collapse:collapse;width:100%}` +
      `th,td{border:1px solid #ddd;padding:6px 10px;font-size:12px;text-align:left}` +
      `th{background:#f3f4f6;text-transform:uppercase;letter-spacing:.04em;font-size:11px}</style></head>` +
      `<body><h2>Attendance</h2><p>${escapeHtml(rangeLabel)}</p>${htmlTable(visibleRows)}</body></html>`
    )
    w.document.close(); w.focus(); w.print()
  }

  return (
    <div className="w-full max-w-6xl mx-auto px-4 sm:px-6 py-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Attendance</h1>
          <p className="text-sm text-gray-500 mt-0.5">{rangeLabel}</p>
        </div>
        <Button size="sm" variant="outline" onClick={() => setExtraOpen(true)}>
          <Plus className="h-4 w-4 mr-1" /> Extra Class
        </Button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <SummaryCard icon={CalendarCheck} label={countLabel} value={kpi.total} tone="indigo" />
        <SummaryCard icon={CheckCircle2} label="Completed" value={kpi.completed} tone="green" />
        <SummaryCard icon={ListChecks} label="Pending" value={kpi.pending} tone="orange" />
        <SummaryCard icon={Percent} label="Attendance Average" value={kpi.avg === null ? '—' : `${kpi.avg}%`} tone="blue" />
      </div>

      {/* Toolbar: quick filters, date picker, search, export */}
      <div className="rounded-xl border border-gray-200 bg-white p-3 space-y-3">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-1.5">
            <FilterPill active={filter === 'today'}     onClick={() => setFilter('today')}>Today</FilterPill>
            <FilterPill active={filter === 'yesterday'} onClick={() => setFilter('yesterday')}>Yesterday</FilterPill>
            <FilterPill active={filter === 'last7'}      onClick={() => setFilter('last7')}>Last 7 Days</FilterPill>
            <Input
              type="date"
              value={pickedDate}
              max={todayISO()}
              onChange={(e) => { if (e.target.value) { setPickedDate(e.target.value); setFilter('date') } }}
              className={`w-[9.5rem] h-8 ${filter === 'date' ? 'ring-1 ring-indigo-300 border-indigo-300' : ''}`}
            />
          </div>
          <div className="flex items-center gap-1.5">
            <Button size="sm" variant="outline" onClick={exportCsv} disabled={!visibleRows.length}>
              <Download className="h-3.5 w-3.5 mr-1" /> CSV
            </Button>
            <Button size="sm" variant="outline" onClick={exportExcel} disabled={!visibleRows.length}>
              <FileSpreadsheet className="h-3.5 w-3.5 mr-1" /> Excel
            </Button>
            <Button size="sm" variant="outline" onClick={printTable} disabled={!visibleRows.length}>
              <Printer className="h-3.5 w-3.5 mr-1" /> Print
            </Button>
          </div>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-600" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search course or section…"
            className="pl-9 h-9"
          />
        </div>
      </div>

      {/* Table */}
      {isError ? (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load attendance. Please refresh.
        </div>
      ) : isLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          {[1, 2, 3, 4, 5].map(n => <div key={n} className="h-12 border-b border-gray-100 bg-gray-50/50 animate-pulse" />)}
        </div>
      ) : visibleRows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 py-16 text-center">
          <CalendarCheck className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-500">
            {search ? 'No classes match your search.' : 'No classes scheduled for this range.'}
          </p>
          {!search && (
            <p className="text-xs text-gray-600 mt-1">
              Classes come from your published timetable. If one is missing, ask your Dean to publish it.
            </p>
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200 text-[11px] uppercase tracking-wide text-gray-500">
                  <th className="text-left font-semibold px-4 py-2.5">Date</th>
                  <th className="text-left font-semibold px-4 py-2.5">Time</th>
                  <th className="text-left font-semibold px-4 py-2.5">Course</th>
                  <th className="text-left font-semibold px-4 py-2.5">Section</th>
                  <th className="text-left font-semibold px-4 py-2.5">Status</th>
                  <th className="text-right font-semibold px-3 py-2.5">Present</th>
                  <th className="text-right font-semibold px-3 py-2.5">Absent</th>
                  <th className="text-right font-semibold px-3 py-2.5">Total</th>
                  <th className="text-right font-semibold px-4 py-2.5">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {visibleRows.map((r) => {
                  const c = r.c
                  const total = c.is_taken ? (c.total_marked ?? 0) : c.student_count
                  const absent = c.is_taken ? (c.total_marked ?? 0) - (c.present_count ?? 0) : null
                  return (
                    <tr key={`${r.date}:${c.course_id}:${c.section_id ?? 'e'}:${c.period_number}`} className="hover:bg-gray-50/70 transition-colors">
                      <td className="px-4 py-2.5 whitespace-nowrap font-medium text-gray-700">{dateLabel(r.date)}</td>
                      <td className="px-4 py-2.5 whitespace-nowrap text-gray-600">
                        <span className="inline-flex items-center gap-1"><Clock className="h-3.5 w-3.5 text-gray-600" />{timeRange(c)}</span>
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs text-gray-500">{c.course_code}</span>
                          <span className="font-medium text-gray-800 truncate max-w-[16rem]">{c.course_title}</span>
                          {c.is_elective && (
                            <span className="rounded bg-violet-100 px-1.5 py-px text-[10px] font-semibold uppercase text-violet-700">Combined</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-gray-600">{sectionLabel(c)}</td>
                      <td className="px-4 py-2.5"><StatusBadge taken={c.is_taken} editable={r.editable} /></td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-emerald-700">{c.is_taken ? c.present_count : '—'}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-rose-600">{absent === null ? '—' : absent}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums text-gray-700">
                        <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5 text-gray-500" />{total}</span>
                      </td>
                      <td className="px-4 py-2.5 text-right"><ActionCell row={r} onOpen={() => openAttendance(r)} /></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ExtraClassDialog
        open={extraOpen}
        onOpenChange={setExtraOpen}
        onStart={(p) => { setExtraOpen(false); navigate(`/sis/attendance/take?${p.toString()}`) }}
      />
    </div>
  )
}

// ── small presentational pieces ─────────────────────────────────────────────
const TONES: Record<string, string> = {
  indigo: 'bg-indigo-50 text-indigo-600',
  green:  'bg-emerald-50 text-emerald-600',
  orange: 'bg-orange-50 text-orange-600',
  blue:   'bg-blue-50 text-blue-600',
}
function SummaryCard({ icon: Icon, label, value, tone }: {
  icon: ComponentType<{ className?: string }>; label: string; value: number | string; tone: string
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 flex items-center gap-3">
      <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ${TONES[tone]}`}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0">
        <p className="text-xl font-bold text-gray-900 leading-none">{value}</p>
        <p className="text-xs text-gray-500 mt-1 truncate">{label}</p>
      </div>
    </div>
  )
}

function FilterPill({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 h-8 rounded-lg text-sm font-medium border transition-colors ${
        active ? 'bg-gray-900 text-white border-gray-900' : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
      }`}
    >
      {children}
    </button>
  )
}

function StatusBadge({ taken, editable }: { taken: boolean; editable: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {taken ? (
        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 text-green-700 px-2 py-0.5 text-xs font-medium">
          <CheckCircle2 className="h-3.5 w-3.5" /> Completed
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 rounded-full bg-orange-100 text-orange-700 px-2 py-0.5 text-xs font-medium">
          Pending
        </span>
      )}
      {!editable && (
        <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 text-gray-500 px-2 py-0.5 text-[11px] font-medium">
          <Lock className="h-3 w-3" /> Read-only
        </span>
      )}
    </span>
  )
}

function ActionCell({ row, onOpen }: { row: Row; onOpen: () => void }) {
  const { c, editable } = row
  if (!c.is_taken && editable) {
    return <Button size="sm" onClick={onOpen}>Take Attendance</Button>
  }
  if (!c.is_taken && !editable) {
    return <span className="inline-flex items-center gap-1 text-xs text-gray-600"><Lock className="h-3.5 w-3.5" /> Locked</span>
  }
  if (c.is_taken && editable) {
    return <Button size="sm" variant="outline" onClick={onOpen}>Edit</Button>
  }
  return <Button size="sm" variant="ghost" onClick={onOpen}>View</Button>
}
