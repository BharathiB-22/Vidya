import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, CalendarRange, Coffee } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { listTemplates } from '@/lib/api/timetable'
import { DAYS_OF_WEEK, formatClockTime, type TimetableTemplateListItem } from '@/types/timetable'

function daySummary(t: TimetableTemplateListItem): string {
  const days = [...t.working_days].sort((a, b) => a - b)
  if (days.length === 0) return 'No working days'
  const first = DAYS_OF_WEEK[days[0]]?.slice(0, 3)
  const last = DAYS_OF_WEEK[days[days.length - 1]]?.slice(0, 3)
  const contiguous = days.every((d, i) => i === 0 || d === days[i - 1] + 1)
  const range = contiguous && days.length > 1 ? `${first}–${last}` : days.map((d) => DAYS_OF_WEEK[d].slice(0, 3)).join(', ')
  return t.saturday_mode === 'HALF' ? `${range} · half Saturday` : range
}

/**
 * Picks the schedule *shape* a timetable is drawn on: which days are worked,
 * how many periods there are, when the breaks fall, what time the day starts.
 *
 * It does not copy anyone's subjects. Templates and timetables are different
 * things — a template is the empty grid, a timetable is what is written in it.
 *
 * Re-templating an existing draft is refused by the server when an entry sits on
 * a period the new template does not teach; that entry would survive in the
 * database but never render again.
 */
export function ChooseTemplateDialog({
  open,
  onOpenChange,
  currentTemplateId,
  hasSlots,
  onChoose,
  isSaving,
  error,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  currentTemplateId: string | null
  hasSlots: boolean
  onChoose: (templateId: string | null) => void
  isSaving: boolean
  error: string | null
}) {
  const [selected, setSelected] = useState<string | null>(currentTemplateId)

  const templatesQ = useQuery({
    queryKey: ['timetable-templates'],
    queryFn: () => listTemplates(),
    enabled: open,
  })
  const templates = templatesQ.data ?? []

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!isSaving) onOpenChange(v) }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Choose a schedule template</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <p className="text-sm text-gray-600">
            A template sets the working days, periods, breaks and clock times this timetable is
            drawn on. It carries no subjects of its own.
          </p>

          {hasSlots && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              This timetable already has entries. A template that does not teach one of their
              periods will be refused, so remove or move those entries first.
            </div>
          )}

          {templatesQ.isLoading ? (
            <div className="h-32 rounded-lg bg-gray-50 animate-pulse" />
          ) : templates.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-200 px-4 py-6 text-center text-sm text-gray-500">
              No templates yet. Create one under the Templates tab.
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {templates.map((t) => {
                const active = selected === t.id
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setSelected(t.id)}
                    className={`flex w-full items-start justify-between gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
                      active
                        ? 'border-indigo-300 bg-indigo-50/60'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{t.name}</p>
                      <p className="text-xs text-gray-500">{t.department_name}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
                        <span className="inline-flex items-center gap-1">
                          <CalendarRange className="h-3 w-3" />
                          {daySummary(t)}
                        </span>
                        <span className="inline-flex items-center gap-1">
                          <Coffee className="h-3 w-3" />
                          {t.period_count} rows
                        </span>
                        <span>
                          {formatClockTime(t.college_start_time)}–{formatClockTime(t.college_end_time)}
                        </span>
                      </div>
                    </div>
                    {active && <Check className="h-4 w-4 shrink-0 text-indigo-600" />}
                  </button>
                )
              })}
            </div>
          )}

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" disabled={isSaving} onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={isSaving || selected === currentTemplateId}
            onClick={() => onChoose(selected)}
          >
            {isSaving ? 'Applying…' : 'Use this template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
