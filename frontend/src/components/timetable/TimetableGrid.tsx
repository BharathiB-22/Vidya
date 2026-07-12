import { useEffect, useMemo, useRef, useState } from 'react'
import { Lock, Move, Pencil, Plus, Trash2, Unlock, X } from 'lucide-react'
import { DAYS_OF_WEEK, formatClockTime, type SaturdayMode, type TimetablePeriod, type TimetableSlot } from '@/types/timetable'

/** A cell the Dean is currently relocating. While one is set the grid enters
 *  "move mode": legal destinations light up and everything else dims. */
export interface MoveTarget {
  day_of_week: number
  period_number: number
}

interface TimetableGridProps {
  slots: TimetableSlot[]
  /** Full period/break configuration from a linked template. Omit to fall back to the old Period 1..8, all-days behavior. */
  periods?: TimetablePeriod[]
  /** Which day-of-week columns (0=Mon..6=Sun) to render. Omit to derive them. */
  workingDays?: number[]
  saturdayMode?: SaturdayMode | null
  editable?: boolean
  onAddSlot?: (dayOfWeek: number, periodNumber: number) => void
  onDeleteSlot?: (slot: TimetableSlot) => void
  /** Extra line under the course title — e.g. section name for a faculty's cross-section view. */
  renderSubLabel?: (slot: TimetableSlot) => string | null

  // --- Workspace-only. Every one optional: the faculty and student pages render
  // this same grid read-only and pass none of them. ---

  onEditSlot?: (slot: TimetableSlot) => void
  /** Called when the Dean picks a destination for `movingSlot`. If the target is
   *  occupied, `occupant` is the slot already there and the caller decides
   *  whether to offer a swap. */
  onMoveSlot?: (slot: TimetableSlot, to: MoveTarget, occupant?: TimetableSlot) => void
  /** Toggle a session lock. Locked cells refuse move, delete and overwrite. */
  onToggleLock?: (slot: TimetableSlot) => void
  /** Session locks, until `timetable_slots.is_locked` exists. */
  lockedSlotIds?: ReadonlySet<string>
}

const DEFAULT_PERIOD_NUMBERS = [1, 2, 3, 4, 5, 6, 7, 8]
/** Only used when no template says otherwise. Saturday and Sunday are not
 *  assumed: a template that teaches on them lists them in `working_days`, and a
 *  stray slot on one keeps its column (see `resolveDays`). */
const DEFAULT_DAYS = [0, 1, 2, 3, 4]
const SATURDAY = 5
/** Roughly four menu rows plus padding — enough to decide which way to open. */
const MENU_HEIGHT_PX = 140
/** Matches the `w-28` time column. */
const TIME_COL_PX = 112
/** The narrowest a day column may get before the grid scrolls instead: enough
 *  for a subject code, a two-line name and a faculty name. */
const MIN_DAY_COL_PX = 150

/**
 * Which day columns to render.
 *
 * The template is the authority — Saturday appears exactly when the chosen
 * template teaches on Saturday, and disappears when it doesn't, without a
 * weekday ever being hard-coded here. Days carrying an entry are added back even
 * if the template dropped them, so an entry can never become invisible (and
 * therefore un-deletable) because the template changed underneath it.
 */
function resolveDays(workingDays: number[] | undefined, slots: TimetableSlot[]): number[] {
  const base = workingDays && workingDays.length > 0 ? workingDays : DEFAULT_DAYS
  const days = new Set(base)
  for (const s of slots) days.add(s.day_of_week)
  return [...days].sort((a, b) => a - b)
}

/** A lock lives in session state today; the day the column exists, only the
 *  source of truth changes. */
function isLocked(slot: TimetableSlot, locked?: ReadonlySet<string>): boolean {
  return slot.is_locked ?? locked?.has(slot.id) ?? false
}

export function TimetableGrid({
  slots,
  periods,
  workingDays,
  saturdayMode,
  editable = false,
  onAddSlot,
  onDeleteSlot,
  renderSubLabel,
  onEditSlot,
  onMoveSlot,
  onToggleLock,
  lockedSlotIds,
}: TimetableGridProps) {
  const days = useMemo(() => resolveDays(workingDays, slots), [workingDays, slots])
  const sortedPeriods = periods ? [...periods].sort((a, b) => a.sequence_number - b.sequence_number) : null

  // The slot being relocated, if any. Escape cancels — a half-finished move is
  // the easiest way to leave the grid in a state the Dean did not intend.
  const [moving, setMoving] = useState<TimetableSlot | null>(null)
  useEffect(() => {
    if (!moving) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMoving(null) }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [moving])

  function findSlot(day: number, period: number): TimetableSlot | undefined {
    return slots.find((s) => s.day_of_week === day && s.period_number === period)
  }

  function handleCellClick(day: number, period: number) {
    if (!moving || !onMoveSlot) return
    if (moving.day_of_week === day && moving.period_number === period) {
      setMoving(null)   // dropped on itself
      return
    }
    const occupant = findSlot(day, period)
    if (occupant && isLocked(occupant, lockedSlotIds)) return   // locked cells refuse
    onMoveSlot(moving, { day_of_week: day, period_number: period }, occupant)
    setMoving(null)
  }

  const inMoveMode = moving !== null

  return (
    <div className="space-y-3">
      {inMoveMode && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-300 bg-slate-50 px-4 py-2.5 text-sm text-slate-700">
          <span>
            Moving <strong className="font-semibold text-slate-900">{moving.course_code}</strong> — click a destination.
            Occupied cells will offer a swap.
          </span>
          <button
            type="button"
            onClick={() => setMoving(null)}
            className="shrink-0 text-xs font-semibold text-slate-600 hover:text-slate-900"
          >
            Cancel (Esc)
          </button>
        </div>
      )}

      {/* The scroll container is what makes the header sticky: `sticky top-0`
          anchors to the nearest scrollport, not the page.

          `table-fixed` lets the day columns share whatever width is available, so
          a wide page gets wide days. But a fixed layout ignores per-cell
          `min-width`, so the floor has to live on the table: below it the
          container scrolls rather than squeezing six days into 90px each. */}
      <div
        data-timetable-scroll
        className="relative overflow-auto rounded-2xl border border-gray-200 bg-white shadow-sm max-h-[calc(100vh-13rem)]"
      >
        <table
          className="w-full text-sm border-collapse table-fixed"
          style={{ minWidth: TIME_COL_PX + days.length * MIN_DAY_COL_PX }}
        >
          <thead>
            <tr className="bg-slate-50">
              {/* The corner cell is sticky on both axes, so it outranks each. */}
              <th className="sticky top-0 left-0 z-30 w-28 px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500 bg-slate-50 border-b border-gray-200">
                Time
              </th>
              {days.map((dayIdx) => (
                <th
                  key={dayIdx}
                  className="sticky top-0 z-20 px-3 py-3 text-center text-xs font-semibold uppercase tracking-wider text-slate-700 bg-slate-50 border-b border-l border-gray-200"
                >
                  {DAYS_OF_WEEK[dayIdx]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedPeriods
              ? sortedPeriods.map((p) => {
                  if (p.period_type === 'BREAK') {
                    return (
                      <tr key={p.id}>
                        <td
                          colSpan={days.length + 1}
                          className="px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-amber-700 bg-amber-50 border-y border-amber-100 text-center"
                        >
                          {p.label ?? 'Break'} · {formatClockTime(p.start_time)}–{formatClockTime(p.end_time)}
                        </td>
                      </tr>
                    )
                  }
                  const periodNumber = p.period_number as number
                  return (
                    <tr key={p.id}>
                      <td className="sticky left-0 z-10 px-4 py-2.5 bg-white border-b border-r border-gray-100 align-middle">
                        <p className="text-xs font-semibold text-gray-900">
                          {p.label ?? `Period ${periodNumber}`}
                        </p>
                        <p className="text-[11px] text-gray-400 tabular-nums">
                          {formatClockTime(p.start_time)}–{formatClockTime(p.end_time)}
                        </p>
                      </td>
                      {days.map((dayIdx) => {
                        const skippedHalfDay = saturdayMode === 'HALF' && dayIdx === SATURDAY && p.skip_on_half_day
                        return (
                          <td
                            key={dayIdx}
                            className="p-1.5 border-b border-l border-gray-100 align-top"
                          >
                            {skippedHalfDay ? (
                              <div className="h-[84px] flex items-center justify-center rounded-xl bg-gray-50 text-[11px] text-gray-300">
                                Half day
                              </div>
                            ) : (
                              <SlotCell
                                slot={findSlot(dayIdx, periodNumber)}
                                editable={editable}
                                onAddSlot={onAddSlot}
                                onDeleteSlot={onDeleteSlot}
                                onEditSlot={onEditSlot}
                                onToggleLock={onToggleLock}
                                onStartMove={onMoveSlot ? setMoving : undefined}
                                lockedSlotIds={lockedSlotIds}
                                renderSubLabel={renderSubLabel}
                                dayIdx={dayIdx}
                                periodNumber={periodNumber}
                                moving={moving}
                                onCellClick={handleCellClick}
                              />
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })
              : DEFAULT_PERIOD_NUMBERS.map((period) => (
                  <tr key={period}>
                    <td className="sticky left-0 z-10 px-4 py-2.5 text-xs font-semibold text-gray-900 bg-white border-b border-r border-gray-100 align-middle">
                      Period {period}
                    </td>
                    {days.map((dayIdx) => (
                      <td
                        key={dayIdx}
                        className="p-1.5 border-b border-l border-gray-100 align-top"
                      >
                        <SlotCell
                          slot={findSlot(dayIdx, period)}
                          editable={editable}
                          onAddSlot={onAddSlot}
                          onDeleteSlot={onDeleteSlot}
                          onEditSlot={onEditSlot}
                          onToggleLock={onToggleLock}
                          onStartMove={onMoveSlot ? setMoving : undefined}
                          lockedSlotIds={lockedSlotIds}
                          renderSubLabel={renderSubLabel}
                          dayIdx={dayIdx}
                          periodNumber={period}
                          moving={moving}
                          onCellClick={handleCellClick}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** Every state of a cell is exactly this tall, so the rows line up across days
 *  whatever a card happens to contain. */
const CELL_HEIGHT = 'h-[84px]'

function SlotCell({
  slot,
  editable,
  onAddSlot,
  onDeleteSlot,
  onEditSlot,
  onToggleLock,
  onStartMove,
  lockedSlotIds,
  renderSubLabel,
  dayIdx,
  periodNumber,
  moving,
  onCellClick,
}: {
  slot: TimetableSlot | undefined
  editable: boolean
  onAddSlot?: (dayOfWeek: number, periodNumber: number) => void
  onDeleteSlot?: (slot: TimetableSlot) => void
  onEditSlot?: (slot: TimetableSlot) => void
  onToggleLock?: (slot: TimetableSlot) => void
  onStartMove?: (slot: TimetableSlot) => void
  lockedSlotIds?: ReadonlySet<string>
  renderSubLabel?: (slot: TimetableSlot) => string | null
  dayIdx: number
  periodNumber: number
  moving: TimetableSlot | null
  onCellClick: (day: number, period: number) => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  // The grid scrolls inside its own container, so a menu on one of the last rows
  // would be clipped by it. Flip upward when there is not room below.
  const [openUp, setOpenUp] = useState(false)
  const cellRef = useRef<HTMLDivElement>(null)

  function toggleMenu() {
    if (!menuOpen && cellRef.current) {
      const scroller = cellRef.current.closest('[data-timetable-scroll]')
      const room = scroller
        ? scroller.getBoundingClientRect().bottom - cellRef.current.getBoundingClientRect().top
        : Number.POSITIVE_INFINITY
      setOpenUp(room < MENU_HEIGHT_PX)
    }
    setMenuOpen((v) => !v)
  }

  useEffect(() => {
    if (!menuOpen) return
    const onDown = (e: MouseEvent) => {
      if (cellRef.current && !cellRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    window.addEventListener('mousedown', onDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  const inMoveMode = moving !== null
  const locked = slot ? isLocked(slot, lockedSlotIds) : false
  const isSource = moving?.id === slot?.id && !!slot

  // In move mode every cell is a destination except the source and locked cells.
  if (inMoveMode && !isSource) {
    const blocked = locked
    return (
      <button
        type="button"
        disabled={blocked}
        onClick={() => onCellClick(dayIdx, periodNumber)}
        className={`flex w-full ${CELL_HEIGHT} flex-col justify-center rounded-xl border-2 border-dashed px-3 text-left transition-colors ${
          blocked
            ? 'border-gray-100 bg-gray-50 cursor-not-allowed'
            : 'border-slate-300 bg-slate-50/60 hover:bg-slate-100'
        }`}
        aria-label={slot ? `Swap with ${slot.course_code}` : 'Move here'}
      >
        {slot ? (
          <>
            <p className="text-sm font-semibold text-gray-400 truncate">{slot.course_code}</p>
            <p className="text-xs text-gray-400">{blocked ? 'Locked' : 'Swap here'}</p>
          </>
        ) : (
          <p className="text-xs font-medium text-slate-500">Move here</p>
        )}
      </button>
    )
  }

  if (slot) {
    const canManage = editable && !inMoveMode
    const subLabel = renderSubLabel?.(slot)
    return (
      <div
        ref={cellRef}
        className={`group relative ${CELL_HEIGHT} overflow-hidden rounded-xl border px-3 py-2 transition-shadow ${
          isSource
            ? 'border-slate-400 bg-slate-100 ring-2 ring-slate-300'
            : locked
              ? 'border-gray-200 bg-gray-50'
              : 'border-gray-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04)] hover:shadow-md'
        }`}
      >
        {/* Subject code, subject name, then who teaches it — the three things a
            Dean scans a grid for, in that order. Room and remarks are edit-time
            detail, not scanning detail, so the card leaves them out. */}
        <div className="flex items-start justify-between gap-1">
          <p className="text-[13px] font-bold leading-tight text-gray-900 truncate">{slot.course_code}</p>
          {locked && <Lock className="mt-px h-3 w-3 shrink-0 text-gray-400" aria-label="Locked" />}
        </div>
        <p className="mt-0.5 text-xs font-medium leading-snug text-gray-700 line-clamp-2">{slot.course_title}</p>
        {slot.faculty_name && (
          <p className="mt-1 text-[11px] leading-tight text-gray-500 truncate">{slot.faculty_name}</p>
        )}
        {subLabel && (
          <p className="text-[11px] leading-tight text-gray-400 truncate">{subLabel}</p>
        )}
        {slot.is_elective && (
          <span className="absolute bottom-1.5 right-2 rounded bg-violet-50 px-1.5 py-px text-[9px] font-semibold uppercase tracking-wide text-violet-600">
            Combined
          </span>
        )}

        {canManage && (
          <button
            type="button"
            onClick={toggleMenu}
            className="absolute top-1 right-1 rounded p-0.5 leading-none text-gray-300 opacity-0 transition-opacity hover:bg-gray-100 hover:text-gray-700 focus:opacity-100 group-hover:opacity-100"
            aria-label={`Actions for ${slot.course_code}`}
            aria-expanded={menuOpen}
          >
            <span className="text-sm leading-none">⋯</span>
          </button>
        )}

        {menuOpen && canManage && (
          <div
            className={`absolute right-1 z-30 w-32 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg ${
              openUp ? 'bottom-6' : 'top-6'
            }`}
          >
            {onEditSlot && (
              <CellMenuItem icon={Pencil} label="Edit" disabled={locked}
                onClick={() => { setMenuOpen(false); onEditSlot(slot) }} />
            )}
            {onStartMove && (
              <CellMenuItem icon={Move} label="Move" disabled={locked}
                onClick={() => { setMenuOpen(false); onStartMove(slot) }} />
            )}
            {onToggleLock && (
              <CellMenuItem icon={locked ? Unlock : Lock} label={locked ? 'Unlock' : 'Lock'}
                onClick={() => { setMenuOpen(false); onToggleLock(slot) }} />
            )}
            {onDeleteSlot && (
              <CellMenuItem icon={Trash2} label="Delete" danger disabled={locked}
                onClick={() => { setMenuOpen(false); onDeleteSlot(slot) }} />
            )}
          </div>
        )}
      </div>
    )
  }

  if (editable && onAddSlot && !inMoveMode) {
    return (
      <button
        type="button"
        onClick={() => onAddSlot(dayIdx, periodNumber)}
        className={`flex w-full ${CELL_HEIGHT} items-center justify-center rounded-xl border border-dashed border-gray-200 text-gray-300 transition-colors hover:border-gray-400 hover:bg-gray-50 hover:text-gray-500`}
        aria-label="Add slot"
      >
        <Plus className="h-4 w-4" />
      </button>
    )
  }
  return <div className={CELL_HEIGHT} />
}

function CellMenuItem({
  icon: Icon,
  label,
  onClick,
  disabled = false,
  danger = false,
}: {
  icon: typeof X
  label: string
  onClick: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      title={disabled ? 'This entry is locked' : undefined}
      className={`flex w-full items-center gap-2 px-3 py-1.5 text-xs font-medium transition-colors ${
        disabled
          ? 'text-gray-300 cursor-not-allowed'
          : danger
            ? 'text-red-600 hover:bg-red-50'
            : 'text-gray-700 hover:bg-gray-50'
      }`}
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}
