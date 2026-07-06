import { Plus, X } from 'lucide-react'
import { DAYS_OF_WEEK, formatClockTime, type SaturdayMode, type TimetablePeriod, type TimetableSlot } from '@/types/timetable'

interface TimetableGridProps {
  slots: TimetableSlot[]
  /** Full period/break configuration from a linked template. Omit to fall back to the old Period 1..8, all-days behavior. */
  periods?: TimetablePeriod[]
  /** Which day-of-week columns (0=Mon..6=Sun) to render. Omit to show all 7. */
  workingDays?: number[]
  saturdayMode?: SaturdayMode | null
  editable?: boolean
  onAddSlot?: (dayOfWeek: number, periodNumber: number) => void
  onDeleteSlot?: (slot: TimetableSlot) => void
  /** Extra line under the course title — e.g. section name for a faculty's cross-section view. */
  renderSubLabel?: (slot: TimetableSlot) => string | null
}

const DEFAULT_PERIOD_NUMBERS = [1, 2, 3, 4, 5, 6, 7, 8]
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]
const SATURDAY = 5

export function TimetableGrid({
  slots,
  periods,
  workingDays,
  saturdayMode,
  editable = false,
  onAddSlot,
  onDeleteSlot,
  renderSubLabel,
}: TimetableGridProps) {
  const days = workingDays && workingDays.length > 0 ? workingDays : ALL_DAYS
  const sortedPeriods = periods ? [...periods].sort((a, b) => a.sequence_number - b.sequence_number) : null

  function findSlot(day: number, period: number): TimetableSlot | undefined {
    return slots.find((s) => s.day_of_week === day && s.period_number === period)
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white">
      <table className="w-full text-sm border-collapse min-w-[720px]">
        <thead>
          <tr>
            <th className="w-24 px-3 py-2 text-left text-xs font-semibold text-gray-400 border-b border-gray-100">
              Time
            </th>
            {days.map((dayIdx) => (
              <th
                key={dayIdx}
                className="px-3 py-2 text-left text-xs font-semibold text-gray-500 border-b border-l border-gray-100"
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
                        className="px-3 py-2 text-xs font-medium text-amber-700 bg-amber-50 border-b border-gray-100 text-center"
                      >
                        {p.label ?? 'Break'} · {formatClockTime(p.start_time)}–{formatClockTime(p.end_time)}
                      </td>
                    </tr>
                  )
                }
                const periodNumber = p.period_number as number
                return (
                  <tr key={p.id}>
                    <td className="px-3 py-2 text-xs font-medium text-gray-400 border-b border-gray-100 align-top">
                      {p.label ?? `Period ${periodNumber}`}
                      <div className="text-[10px] text-gray-300">
                        {formatClockTime(p.start_time)}–{formatClockTime(p.end_time)}
                      </div>
                    </td>
                    {days.map((dayIdx) => {
                      const skippedHalfDay = saturdayMode === 'HALF' && dayIdx === SATURDAY && p.skip_on_half_day
                      const slot = findSlot(dayIdx, periodNumber)
                      return (
                        <td
                          key={dayIdx}
                          className="px-2 py-1.5 border-b border-l border-gray-100 align-top min-w-[110px]"
                        >
                          {skippedHalfDay ? (
                            <div className="min-h-[48px] flex items-center justify-center rounded-lg bg-gray-50 text-[10px] text-gray-300">
                              Half day
                            </div>
                          ) : (
                            <SlotCell
                              slot={slot}
                              editable={editable}
                              onAddSlot={onAddSlot}
                              onDeleteSlot={onDeleteSlot}
                              renderSubLabel={renderSubLabel}
                              dayIdx={dayIdx}
                              periodNumber={periodNumber}
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
                  <td className="px-3 py-2 text-xs font-medium text-gray-400 border-b border-gray-100 align-top">
                    Period {period}
                  </td>
                  {days.map((dayIdx) => (
                    <td
                      key={dayIdx}
                      className="px-2 py-1.5 border-b border-l border-gray-100 align-top min-w-[110px]"
                    >
                      <SlotCell
                        slot={findSlot(dayIdx, period)}
                        editable={editable}
                        onAddSlot={onAddSlot}
                        onDeleteSlot={onDeleteSlot}
                        renderSubLabel={renderSubLabel}
                        dayIdx={dayIdx}
                        periodNumber={period}
                      />
                    </td>
                  ))}
                </tr>
              ))}
        </tbody>
      </table>
    </div>
  )
}

function SlotCell({
  slot,
  editable,
  onAddSlot,
  onDeleteSlot,
  renderSubLabel,
  dayIdx,
  periodNumber,
}: {
  slot: TimetableSlot | undefined
  editable: boolean
  onAddSlot?: (dayOfWeek: number, periodNumber: number) => void
  onDeleteSlot?: (slot: TimetableSlot) => void
  renderSubLabel?: (slot: TimetableSlot) => string | null
  dayIdx: number
  periodNumber: number
}) {
  if (slot) {
    return (
      <div className="rounded-lg bg-indigo-50 border border-indigo-100 px-2 py-1.5 relative group">
        <p className="text-xs font-semibold text-indigo-900 truncate">{slot.course_code}</p>
        <p className="text-[11px] text-indigo-700 truncate">{slot.course_title}</p>
        {slot.faculty_name && (
          <p className="text-[11px] text-gray-500 truncate">{slot.faculty_name}</p>
        )}
        {slot.room && <p className="text-[11px] text-gray-400 truncate">Room {slot.room}</p>}
        {renderSubLabel && (
          <p className="text-[11px] text-gray-400 truncate">{renderSubLabel(slot)}</p>
        )}
        {editable && onDeleteSlot && (
          <button
            type="button"
            onClick={() => onDeleteSlot(slot)}
            className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-red-500"
            aria-label="Remove slot"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    )
  }
  if (editable && onAddSlot) {
    return (
      <button
        type="button"
        onClick={() => onAddSlot(dayIdx, periodNumber)}
        className="w-full h-full min-h-[48px] flex items-center justify-center rounded-lg border border-dashed border-gray-200 text-gray-300 hover:border-indigo-300 hover:text-indigo-400 transition-colors"
        aria-label="Add slot"
      >
        <Plus className="h-3.5 w-3.5" />
      </button>
    )
  }
  return <div className="min-h-[48px]" />
}
