import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Search, GraduationCap, UserCheck, BookOpen, LayoutList, X, Loader2 } from 'lucide-react'
import { sisApi } from '@/lib/api/sis'
import type { StudentHit, FacultyHit, SectionHit, CourseHit } from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Types & helpers
// ---------------------------------------------------------------------------

type Hit =
  | { kind: 'student'; data: StudentHit }
  | { kind: 'faculty'; data: FacultyHit }
  | { kind: 'section'; data: SectionHit }
  | { kind: 'course';  data: CourseHit  }

function hitPath(hit: Hit): string {
  switch (hit.kind) {
    case 'student': return `/sis/directory/students/${hit.data.id}`
    case 'faculty': return `/sis/directory/faculty/${hit.data.id}`
    case 'section': return `/sis/roster`
    case 'course':  return `/programs`
  }
}

function hitLabel(hit: Hit): string {
  switch (hit.kind) {
    case 'student': return hit.data.full_name
    case 'faculty': return hit.data.full_name
    case 'section': return hit.data.name
    case 'course':  return `${hit.data.code} — ${hit.data.title}`
  }
}

function hitSub(hit: Hit): string | null {
  switch (hit.kind) {
    case 'student': return hit.data.usn ? `USN ${hit.data.usn}` : hit.data.email
    case 'faculty': return hit.data.employee_id ? `EMP ${hit.data.employee_id}` : hit.data.email
    case 'section': return hit.data.is_active ? 'Active section' : 'Inactive section'
    case 'course':  return null
  }
}

const KIND_META: Record<Hit['kind'], { label: string; color: string; Icon: React.ElementType }> = {
  student: { label: 'Student',  color: '#a5b4fc', Icon: GraduationCap },
  faculty: { label: 'Faculty',  color: '#34d399', Icon: UserCheck },
  section: { label: 'Section',  color: '#fbbf24', Icon: LayoutList },
  course:  { label: 'Course',   color: '#f472b6', Icon: BookOpen },
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  open: boolean
  onClose: () => void
}

export function SearchPalette({ open, onClose }: Props) {
  const navigate   = useNavigate()
  const inputRef   = useRef<HTMLInputElement>(null)
  const listRef    = useRef<HTMLDivElement>(null)

  const [query, setQuery]     = useState('')
  const [debounced, setDebounced] = useState('')
  const [cursor, setCursor]   = useState(0)

  // Debounce
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query), 250)
    return () => clearTimeout(t)
  }, [query])

  // Focus input when opened
  useEffect(() => {
    if (open) { setQuery(''); setCursor(0); setTimeout(() => inputRef.current?.focus(), 30) }
  }, [open])

  // Escape closes
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    if (open) document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const { data, isFetching } = useQuery({
    queryKey: ['sis-search', debounced],
    queryFn:  () => sisApi.search(debounced),
    enabled:  debounced.length >= 2,
    staleTime: 10_000,
  })

  // Build flat list for keyboard nav
  const hits: Hit[] = data ? [
    ...data.students.map(d => ({ kind: 'student' as const, data: d })),
    ...data.faculty.map(d  => ({ kind: 'faculty' as const, data: d })),
    ...data.sections.map(d => ({ kind: 'section' as const, data: d })),
    ...data.courses.map(d  => ({ kind: 'course'  as const, data: d })),
  ] : []

  const navigate_to = useCallback((hit: Hit) => {
    navigate(hitPath(hit))
    onClose()
  }, [navigate, onClose])

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, hits.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
    if (e.key === 'Enter' && hits[cursor]) navigate_to(hits[cursor])
  }

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${cursor}"]`) as HTMLElement | null
    el?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  if (!open) return null

  const hasResults = hits.length > 0
  const showEmpty  = debounced.length >= 2 && !isFetching && !hasResults
  const showHint   = debounced.length < 2

  // Group hits for display
  const groups: { kind: Hit['kind']; items: Hit[] }[] = []
  const kindOrder: Hit['kind'][] = ['student', 'faculty', 'section', 'course']
  for (const kind of kindOrder) {
    const items = hits.filter(h => h.kind === kind)
    if (items.length) groups.push({ kind, items })
  }

  let flatIdx = 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[12vh] px-4"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" />

      {/* Palette panel */}
      <div
        className="relative w-full max-w-xl rounded-2xl shadow-2xl overflow-hidden"
        style={{ background: '#12121e', border: '1px solid rgba(255,255,255,0.1)' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Input row */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/8">
          {isFetching
            ? <Loader2 size={17} className="text-slate-500 animate-spin flex-shrink-0" />
            : <Search size={17} className="text-slate-500 flex-shrink-0" />
          }
          <input
            ref={inputRef}
            value={query}
            onChange={e => { setQuery(e.target.value); setCursor(0) }}
            onKeyDown={onKeyDown}
            placeholder="Search students, faculty, sections, courses…"
            className="flex-1 bg-transparent text-slate-200 placeholder-slate-600 text-sm outline-none"
          />
          {query && (
            <button onClick={() => { setQuery(''); setDebounced(''); inputRef.current?.focus() }}
              className="text-slate-600 hover:text-slate-400">
              <X size={15} />
            </button>
          )}
        </div>

        {/* Results */}
        <div ref={listRef} className="max-h-[60vh] overflow-y-auto py-2">
          {showHint && (
            <p className="text-center text-slate-600 text-xs py-8">Type at least 2 characters to search</p>
          )}
          {showEmpty && (
            <p className="text-center text-slate-600 text-xs py-8">No results for "{debounced}"</p>
          )}
          {groups.map(({ kind, items }) => {
            const meta = KIND_META[kind]
            return (
              <div key={kind}>
                <div className="px-4 py-1.5 flex items-center gap-2">
                  <meta.Icon size={11} style={{ color: meta.color }} />
                  <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: meta.color }}>
                    {meta.label}s
                  </span>
                </div>
                {items.map(hit => {
                  const idx = flatIdx++
                  const active = cursor === idx
                  const sub = hitSub(hit)
                  return (
                    <button
                      key={`${hit.kind}-${hit.data.id}`}
                      data-idx={idx}
                      onClick={() => navigate_to(hit)}
                      onMouseEnter={() => setCursor(idx)}
                      className="w-full text-left px-4 py-2.5 flex items-center gap-3 transition-colors"
                      style={{ background: active ? 'rgba(255,255,255,0.06)' : 'transparent' }}
                    >
                      <div className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
                        style={{ background: `${meta.color}18` }}>
                        <meta.Icon size={14} style={{ color: meta.color }} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-200 truncate">{hitLabel(hit)}</p>
                        {sub && <p className="text-xs text-slate-600 truncate mt-0.5">{sub}</p>}
                      </div>
                      {active && (
                        <kbd className="text-[9px] text-slate-600 border border-white/10 rounded px-1.5 py-0.5 flex-shrink-0">↵</kbd>
                      )}
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="px-4 py-2 border-t border-white/6 flex items-center gap-3 text-[10px] text-slate-700">
          <span><kbd className="bg-white/8 px-1 rounded">↑↓</kbd> navigate</span>
          <span><kbd className="bg-white/8 px-1 rounded">↵</kbd> open</span>
          <span><kbd className="bg-white/8 px-1 rounded">Esc</kbd> close</span>
        </div>
      </div>
    </div>
  )
}
