import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Archive, CalendarClock, ChevronDown, ChevronLeft, ChevronUp,
  ClipboardCheck, Pencil, Plus, Rocket, Settings2, Trash2, X,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { TimetableGrid } from '@/components/timetable/TimetableGrid'
import { academicsApi } from '@/lib/api/academics'
import { assignmentsApi } from '@/lib/api/assignments'
import {
  listTimetables, createTimetable, getTimetable,
  addSlot, deleteSlot, submitTimetable, publishTimetable,
  listPendingTimetables, approveTimetable, rejectTimetable,
  listTemplates, createTemplate, getTemplate, updateTemplate, deleteTemplate,
  addPeriod, deletePeriod,
} from '@/lib/api/timetable'
import { getErrorMessage } from '@/lib/api'
import {
  DAYS_OF_WEEK, BREAK_PRESETS, formatClockTime,
  type TimetableSlot, type SaturdayMode, type PeriodType, type TimetableListItem,
  type TimetableTemplateListItem, type CreatePeriodPayload,
} from '@/types/timetable'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:           'bg-gray-100 text-gray-600',
  PENDING_REVIEW:  'bg-yellow-50 text-yellow-700',
  APPROVED:        'bg-blue-50 text-blue-700',
  REJECTED:        'bg-red-50 text-red-700',
  PUBLISHED:       'bg-green-50 text-green-700',
}

/** Unambiguous timetable label: "MCA · Semester 1 · Section A" instead of a
 *  bare "Section A". Falls back gracefully when the program/semester chain is
 *  incomplete. */
function timetableLabel(t: {
  program_name?: string | null
  semester_label?: string | null
  section_name?: string | null
}): string {
  return [t.program_name, t.semester_label, t.section_name ? `Section ${t.section_name}` : null]
    .filter(Boolean)
    .join(' · ') || 'Section'
}

// ---------------------------------------------------------------------------
// Templates — academic schedule configuration (working days, periods, breaks)
// ---------------------------------------------------------------------------

const HHMM = /^(\d{1,2}):(\d{2})$/
function hhmmToMin(t: string): number | null {
  const m = HHMM.exec(t)
  if (!m) return null
  return Number(m[1]) * 60 + Number(m[2])
}
function minToHms(m: number): string {
  const h = Math.floor(m / 60), mm = m % 60
  return `${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}:00`
}

interface GenBreak { afterPeriod: number; label: string; minutes: number }

/** Build a full PERIOD/BREAK sequence from college timings — the same shape a
 *  Dean would otherwise create by hand, one row at a time (Part 2). Periods are
 *  packed from start time using `periodMins`; each break is inserted right after
 *  its `afterPeriod`. Generation stops when the next period would run past the
 *  college end time. */
function generatePeriods(
  startTime: string, endTime: string, periodMins: number, breaks: GenBreak[],
): CreatePeriodPayload[] {
  const start = hhmmToMin(startTime), end = hhmmToMin(endTime)
  if (start == null || end == null || periodMins <= 0 || end <= start) return []
  const rows: CreatePeriodPayload[] = []
  let cursor = start
  let periodNumber = 1
  let seq = 1
  // Cap to a sane number of periods to avoid a runaway loop on bad input.
  while (cursor + periodMins <= end && periodNumber <= 15) {
    rows.push({
      sequence_number: seq++,
      period_type: 'PERIOD',
      period_number: periodNumber,
      start_time: minToHms(cursor),
      end_time: minToHms(cursor + periodMins),
    })
    cursor += periodMins
    for (const b of breaks) {
      if (b.afterPeriod === periodNumber && b.minutes > 0 && cursor + b.minutes <= end) {
        rows.push({
          sequence_number: seq++,
          period_type: 'BREAK',
          label: b.label,
          start_time: minToHms(cursor),
          end_time: minToHms(cursor + b.minutes),
        })
        cursor += b.minutes
      }
    }
    periodNumber++
  }
  return rows
}

function CreateTemplateDialog({
  open, onOpenChange, onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: (id: string) => void
}) {
  const queryClient = useQueryClient()
  const [departmentId, setDepartmentId] = useState('')
  const [name, setName] = useState('')
  const [days, setDays] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]))
  const [saturdayMode, setSaturdayMode] = useState<SaturdayMode>('HOLIDAY')
  const [startTime, setStartTime] = useState('08:30')
  const [endTime, setEndTime] = useState('16:00')
  // Auto-generation timings (Part 2)
  const [autoGenerate, setAutoGenerate] = useState(true)
  const [periodMins, setPeriodMins] = useState('50')
  const [teaMins, setTeaMins] = useState('15')
  const [teaAfter, setTeaAfter] = useState('2')
  const [lunchMins, setLunchMins] = useState('45')
  const [lunchAfter, setLunchAfter] = useState('4')
  const [error, setError] = useState<string | null>(null)

  const departmentsQ = useQuery({ queryKey: ['departments-for-template'], queryFn: () => academicsApi.listDepartments() })

  function toggleDay(d: number) {
    setDays((prev) => {
      const next = new Set(prev)
      if (next.has(d)) next.delete(d)
      else next.add(d)
      return next
    })
  }

  const previewRows = autoGenerate
    ? generatePeriods(startTime, endTime, Number(periodMins), [
        { afterPeriod: Number(teaAfter), label: 'Tea Break', minutes: Number(teaMins) },
        { afterPeriod: Number(lunchAfter), label: 'Lunch Break', minutes: Number(lunchMins) },
      ])
    : []

  const createMut = useMutation({
    mutationFn: async () => {
      const workingDays = new Set(days)
      if (saturdayMode === 'HOLIDAY') workingDays.delete(5)
      else workingDays.add(5)
      const created = await createTemplate({
        department_id: departmentId,
        name,
        working_days: [...workingDays].sort(),
        saturday_mode: saturdayMode,
        college_start_time: `${startTime}:00`,
        college_end_time: `${endTime}:00`,
      })
      // Auto-generate the period/break sequence from the timings, sequentially
      // (add_period enforces per-template uniqueness). Editable afterwards.
      if (autoGenerate) {
        for (const row of previewRows) {
          await addPeriod(created.id, row)
        }
      }
      return created
    },
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['timetable-templates'] })
      onOpenChange(false)
      setName(''); setDepartmentId(''); setError(null)
      // Jump straight into the new template's builder (working days/periods/
      // breaks) instead of leaving the Dean on the plain list view.
      onCreated(created.id)
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const canSubmit = !!departmentId && !!name.trim() && !!startTime && !!endTime

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Timetable Template</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Department</label>
            <Select value={departmentId} onValueChange={setDepartmentId}>
              <SelectTrigger><SelectValue placeholder="Select department" /></SelectTrigger>
              <SelectContent>
                {(departmentsQ.data ?? []).map((d) => (
                  <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Template Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. MCA Standard Schedule" />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Working Days</label>
            <div className="flex flex-wrap gap-1.5">
              {DAYS_OF_WEEK.slice(0, 5).map((label, idx) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => toggleDay(idx)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    days.has(idx) ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-gray-200 text-gray-500'
                  }`}
                >
                  {label.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Saturday</label>
            <div className="flex gap-1.5">
              {(['FULL', 'HALF', 'HOLIDAY'] as SaturdayMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setSaturdayMode(mode)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    saturdayMode === mode ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-gray-200 text-gray-500'
                  }`}
                >
                  {mode === 'FULL' ? 'Full Day' : mode === 'HALF' ? 'Half Day' : 'Holiday'}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">College Start Time</label>
              <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">College End Time</label>
              <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
            </div>
          </div>

          <label className="flex items-center gap-2 text-xs font-medium text-gray-700 pt-1">
            <input type="checkbox" checked={autoGenerate} onChange={(e) => setAutoGenerate(e.target.checked)} />
            Auto-generate periods &amp; breaks from timings
          </label>

          {autoGenerate && (
            <div className="rounded-lg border border-gray-200 bg-gray-50/60 p-3 space-y-3">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block text-[11px] text-gray-500 mb-1">Period (min)</label>
                  <Input type="number" min={5} value={periodMins} onChange={(e) => setPeriodMins(e.target.value)} />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-500 mb-1">Tea (min)</label>
                  <Input type="number" min={0} value={teaMins} onChange={(e) => setTeaMins(e.target.value)} />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-500 mb-1">Tea after period</label>
                  <Input type="number" min={1} value={teaAfter} onChange={(e) => setTeaAfter(e.target.value)} />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-500 mb-1">Lunch (min)</label>
                  <Input type="number" min={0} value={lunchMins} onChange={(e) => setLunchMins(e.target.value)} />
                </div>
                <div>
                  <label className="block text-[11px] text-gray-500 mb-1">Lunch after period</label>
                  <Input type="number" min={1} value={lunchAfter} onChange={(e) => setLunchAfter(e.target.value)} />
                </div>
              </div>
              {previewRows.length > 0 ? (
                <div className="max-h-40 overflow-y-auto rounded border border-gray-100 bg-white divide-y divide-gray-50">
                  {previewRows.map((r, i) => (
                    <div key={i} className="flex items-center justify-between px-2.5 py-1 text-[11px]">
                      <span className={r.period_type === 'BREAK' ? 'text-amber-700 font-medium' : 'text-gray-700'}>
                        {r.period_type === 'BREAK' ? r.label : `Period ${r.period_number}`}
                      </span>
                      <span className="text-gray-400">
                        {r.start_time.slice(0, 5)}–{r.end_time.slice(0, 5)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-gray-400">Enter valid timings to preview the generated schedule.</p>
              )}
            </div>
          )}

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canSubmit || createMut.isPending} onClick={() => createMut.mutate()}>
            {createMut.isPending
              ? (autoGenerate ? 'Generating…' : 'Creating…')
              : (autoGenerate ? 'Generate Template' : 'Create Template')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function EditTemplateDialog({
  open, onOpenChange, template,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  template: TimetableTemplateListItem
}) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(template.name)
  const [days, setDays] = useState<Set<number>>(new Set(template.working_days.filter((d) => d !== 5)))
  const [saturdayMode, setSaturdayMode] = useState<SaturdayMode>(template.saturday_mode ?? 'HOLIDAY')
  const [startTime, setStartTime] = useState(template.college_start_time.slice(0, 5))
  const [endTime, setEndTime] = useState(template.college_end_time.slice(0, 5))
  const [error, setError] = useState<string | null>(null)

  function toggleDay(d: number) {
    setDays((prev) => {
      const next = new Set(prev)
      if (next.has(d)) next.delete(d)
      else next.add(d)
      return next
    })
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const workingDays = new Set(days)
      if (saturdayMode === 'HOLIDAY') workingDays.delete(5)
      else workingDays.add(5)
      return updateTemplate(template.id, {
        name,
        working_days: [...workingDays].sort(),
        saturday_mode: saturdayMode,
        college_start_time: `${startTime}:00`,
        college_end_time: `${endTime}:00`,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timetable-templates'] })
      queryClient.invalidateQueries({ queryKey: ['timetable-template-detail', template.id] })
      onOpenChange(false)
      setError(null)
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const canSubmit = !!name.trim() && !!startTime && !!endTime

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Edit Template</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Template Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Working Days</label>
            <div className="flex flex-wrap gap-1.5">
              {DAYS_OF_WEEK.slice(0, 5).map((label, idx) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => toggleDay(idx)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    days.has(idx) ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-gray-200 text-gray-500'
                  }`}
                >
                  {label.slice(0, 3)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Saturday</label>
            <div className="flex gap-1.5">
              {(['FULL', 'HALF', 'HOLIDAY'] as SaturdayMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setSaturdayMode(mode)}
                  className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                    saturdayMode === mode ? 'bg-indigo-600 border-indigo-600 text-white' : 'border-gray-200 text-gray-500'
                  }`}
                >
                  {mode === 'FULL' ? 'Full Day' : mode === 'HALF' ? 'Half Day' : 'Holiday'}
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">College Start Time</label>
              <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">College End Time</label>
              <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
            </div>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canSubmit || saveMut.isPending} onClick={() => saveMut.mutate()}>
            {saveMut.isPending ? 'Saving…' : 'Save Changes'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AddPeriodDialog({
  open, onOpenChange, templateId, mode, saturdayMode,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  templateId: string
  mode: PeriodType
  saturdayMode: SaturdayMode | null
}) {
  const queryClient = useQueryClient()
  const [sequenceNumber, setSequenceNumber] = useState('1')
  const [periodNumber, setPeriodNumber] = useState('1')
  const [breakPreset, setBreakPreset] = useState(BREAK_PRESETS[0])
  const [customLabel, setCustomLabel] = useState('')
  const [startTime, setStartTime] = useState('08:30')
  const [endTime, setEndTime] = useState('09:20')
  const [skipOnHalfDay, setSkipOnHalfDay] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isCustomBreak = breakPreset === 'Custom'

  const addMut = useMutation({
    mutationFn: () =>
      addPeriod(templateId, {
        sequence_number: Number(sequenceNumber),
        period_type: mode,
        period_number: mode === 'PERIOD' ? Number(periodNumber) : null,
        label: mode === 'BREAK' ? (isCustomBreak ? customLabel : breakPreset) : null,
        start_time: `${startTime}:00`,
        end_time: `${endTime}:00`,
        skip_on_half_day: skipOnHalfDay,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timetable-template-detail', templateId] })
      onOpenChange(false)
      setError(null)
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{mode === 'PERIOD' ? 'Add Period' : 'Add Break'}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Row order (sequence)</label>
            <Input type="number" min={1} value={sequenceNumber} onChange={(e) => setSequenceNumber(e.target.value)} />
          </div>
          {mode === 'PERIOD' ? (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Period Number</label>
              <Input type="number" min={1} value={periodNumber} onChange={(e) => setPeriodNumber(e.target.value)} />
            </div>
          ) : (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Break Type</label>
              <Select value={breakPreset} onValueChange={setBreakPreset}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {BREAK_PRESETS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                  <SelectItem value="Custom">Custom…</SelectItem>
                </SelectContent>
              </Select>
              {isCustomBreak && (
                <Input
                  className="mt-2"
                  value={customLabel}
                  onChange={(e) => setCustomLabel(e.target.value)}
                  placeholder="Break name"
                />
              )}
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">Start Time</label>
              <Input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">End Time</label>
              <Input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
            </div>
          </div>
          {saturdayMode === 'HALF' && (
            <label className="flex items-center gap-2 text-xs text-gray-600">
              <input type="checkbox" checked={skipOnHalfDay} onChange={(e) => setSkipOnHalfDay(e.target.checked)} />
              Skip this row on Saturday (Half Day)
            </label>
          )}
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={addMut.isPending || (mode === 'BREAK' && isCustomBreak && !customLabel.trim())}
            onClick={() => addMut.mutate()}
          >
            {addMut.isPending ? 'Adding…' : 'Add'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TemplateDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const queryClient = useQueryClient()
  const [addDialogMode, setAddDialogMode] = useState<PeriodType | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['timetable-template-detail', id],
    queryFn: () => getTemplate(id),
  })

  const deleteMut = useMutation({
    mutationFn: (periodId: string) => deletePeriod(id, periodId),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['timetable-template-detail', id] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  if (isLoading || !data) {
    return <div className="h-64 rounded-xl bg-gray-50 animate-pulse" />
  }

  const sortedPeriods = [...data.periods].sort((a, b) => a.sequence_number - b.sequence_number)

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
        <ChevronLeft className="h-4 w-4" /> Back to templates
      </button>

      <div>
        <h2 className="text-lg font-semibold text-gray-900">{data.name}</h2>
        <p className="text-xs text-gray-600 mt-0.5">
          {data.department_name} · {data.working_days.map((d) => DAYS_OF_WEEK[d].slice(0, 3)).join(', ')}
          {data.saturday_mode && data.saturday_mode !== 'HOLIDAY' && ` (Sat: ${data.saturday_mode})`}
          {' · '}{formatClockTime(data.college_start_time)}–{formatClockTime(data.college_end_time)}
        </p>
      </div>

      <div className="flex gap-2">
        <Button size="sm" onClick={() => setAddDialogMode('PERIOD')}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add Period
        </Button>
        <Button size="sm" variant="outline" onClick={() => setAddDialogMode('BREAK')}>
          <Plus className="h-3.5 w-3.5 mr-1" /> Add Break
        </Button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      {sortedPeriods.length === 0 ? (
        <div className="text-center py-10 rounded-xl border border-dashed border-gray-200">
          <p className="text-sm text-gray-400">No periods configured yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {sortedPeriods.map((p) => (
            <div key={p.id} className="px-5 py-3 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-gray-800">
                  {p.period_type === 'BREAK' ? (p.label ?? 'Break') : (p.label ?? `Period ${p.period_number}`)}
                  {p.period_type === 'BREAK' && <span className="ml-2 text-[10px] uppercase text-amber-600">Break</span>}
                </p>
                <p className="text-xs text-gray-600">
                  {formatClockTime(p.start_time)}–{formatClockTime(p.end_time)}
                  {p.skip_on_half_day && ' · Skipped on Saturday Half Day'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => deleteMut.mutate(p.id)}
                className="text-gray-300 hover:text-red-500"
                aria-label="Remove"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      {addDialogMode && (
        <AddPeriodDialog
          open={!!addDialogMode}
          onOpenChange={(v) => !v && setAddDialogMode(null)}
          templateId={id}
          mode={addDialogMode}
          saturdayMode={data.saturday_mode}
        />
      )}
    </div>
  )
}

function TemplatesTab() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<TimetableTemplateListItem | null>(null)
  const [deleting, setDeleting] = useState<TimetableTemplateListItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['timetable-templates'],
    queryFn: () => listTemplates(),
    enabled: !selectedId,
  })

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteTemplate(id),
    onSuccess: () => {
      setDeleting(null)
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['timetable-templates'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  if (selectedId) {
    return <TemplateDetail id={selectedId} onBack={() => setSelectedId(null)} />
  }

  const items = data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-gray-400">
          Configure working days, college hours, periods, and breaks before building section timetables.
        </p>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-3.5 w-3.5 mr-1" /> New Template
        </Button>
      </div>

      {(isError || error) && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error ?? 'Failed to load templates. Please refresh.'}
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">{[1, 2].map((n) => <div key={n} className="h-14 rounded-xl bg-gray-50 animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <Settings2 className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No templates configured yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((t) => (
            <div key={t.id} className="flex items-center justify-between gap-2 px-5 py-4 hover:bg-gray-50 transition-colors">
              <button onClick={() => setSelectedId(t.id)} className="flex-1 text-left min-w-0">
                <span className="text-sm font-semibold text-gray-800">{t.name}</span>
                <p className="text-xs text-gray-600">
                  {t.department_name}
                  {' · '}{t.working_days.map((d) => DAYS_OF_WEEK[d].slice(0, 3)).join(', ')}
                  {' · '}{formatClockTime(t.college_start_time)}–{formatClockTime(t.college_end_time)}
                </p>
              </button>
              <span className="text-xs text-gray-500 shrink-0">{t.period_count} rows</span>
              <button
                type="button"
                onClick={() => setEditing(t)}
                className="p-1.5 text-gray-400 hover:text-indigo-600 shrink-0"
                aria-label="Edit template"
              >
                <Pencil className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setDeleting(t)}
                className="p-1.5 text-gray-400 hover:text-red-500 shrink-0"
                aria-label="Delete template"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      <CreateTemplateDialog open={creating} onOpenChange={setCreating} onCreated={setSelectedId} />
      {editing && (
        <EditTemplateDialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)} template={editing} />
      )}

      <Dialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Delete template?</DialogTitle></DialogHeader>
          <p className="text-sm text-gray-600">
            Delete <strong>{deleting?.name}</strong> and all its periods? Timetables built from it keep
            working but revert to the default period grid. This can’t be undone.
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={deleteMut.isPending}
              onClick={() => deleting && deleteMut.mutate(deleting.id)}
            >
              {deleteMut.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Timetables — section-wise, built against a template
// ---------------------------------------------------------------------------

function AddSlotDialog({
  open, onOpenChange, semesterId, sectionId, dayOfWeek, periodNumber, onSubmit, isSubmitting, error,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  semesterId: string
  sectionId: string
  dayOfWeek: number | null
  periodNumber: number | null
  onSubmit: (payload: { course_id: string; faculty_user_id?: string; room?: string; remarks?: string }) => void
  isSubmitting: boolean
  error: string | null
}) {
  const [courseId, setCourseId] = useState<string>('')
  const [facultyUserId, setFacultyUserId] = useState<string>('')
  const [room, setRoom] = useState('')
  const [remarks, setRemarks] = useState('')

  // Every course in this semester's program is selectable, whether or not it
  // has a faculty assignment yet: zero -> save with no faculty, one -> auto-
  // fill, more than one -> show a picker.
  const coursesQ = useQuery({
    queryKey: ['courses-for-slot', semesterId, sectionId],
    queryFn: () => assignmentsApi.listCoursesForSlot(semesterId, sectionId),
    enabled: open,
  })

  const courses = coursesQ.data ?? []
  const selectedCourse = courses.find((c) => c.course_id === courseId)
  const facultyForCourse = selectedCourse?.assignments ?? []
  const needsFacultyPicker = facultyForCourse.length > 1

  function handleCourseChange(id: string) {
    setCourseId(id)
    const options = courses.find((c) => c.course_id === id)?.assignments ?? []
    setFacultyUserId(options.length === 1 ? (options[0].faculty_user_id ?? '') : '')
  }

  const resolvedFacultyName = facultyForCourse.length === 1
    ? (facultyForCourse[0].faculty?.full_name ?? 'Unassigned faculty')
    : null

  const canSubmit = !!courseId && (!needsFacultyPicker || !!facultyUserId)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            Add slot — {dayOfWeek != null ? DAYS_OF_WEEK[dayOfWeek] : ''} · Period {periodNumber}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Course</label>
            <Select value={courseId} onValueChange={handleCourseChange}>
              <SelectTrigger>
                <SelectValue placeholder={coursesQ.isLoading ? 'Loading…' : 'Select a course'} />
              </SelectTrigger>
              <SelectContent>
                {courses.map((c) => (
                  <SelectItem key={c.course_id} value={c.course_id}>{c.code} — {c.title}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!coursesQ.isLoading && courses.length === 0 && (
              <p className="text-xs text-gray-500 mt-1">
                No courses found for this semester.
              </p>
            )}
          </div>

          {needsFacultyPicker ? (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Faculty</label>
              <Select value={facultyUserId} onValueChange={setFacultyUserId}>
                <SelectTrigger><SelectValue placeholder="Multiple faculty teach this course — pick one" /></SelectTrigger>
                <SelectContent>
                  {facultyForCourse.map((a) => (
                    <SelectItem key={a.id} value={a.faculty_user_id ?? ''}>
                      {a.faculty?.full_name ?? 'Unassigned faculty'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : resolvedFacultyName ? (
            <div>
              <label className="block text-xs text-gray-500 mb-1">Faculty</label>
              <p className="text-sm text-gray-900 px-3 py-2 rounded-md border border-gray-200 bg-gray-50">
                {resolvedFacultyName}
              </p>
            </div>
          ) : courseId ? (
            <p className="text-xs text-gray-500">
              No faculty assigned to this course yet — the slot can still be saved without one.
            </p>
          ) : null}

          <div>
            <label className="block text-xs text-gray-500 mb-1">Room / Lab (optional)</label>
            <Input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="e.g. Block A, Room 204" />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Remarks (optional)</label>
            <Input value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="e.g. Tutorial, Guest lecture" />
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={!canSubmit || isSubmitting}
            onClick={() => {
              if (!courseId) return
              onSubmit({
                course_id: courseId,
                faculty_user_id: facultyUserId || undefined,
                room: room || undefined,
                remarks: remarks || undefined,
              })
            }}
          >
            {isSubmitting ? 'Adding…' : 'Add Slot'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TimetableDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const queryClient = useQueryClient()
  const [dialogCell, setDialogCell] = useState<{ day: number; period: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['timetable-detail', id],
    queryFn: () => getTimetable(id),
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['timetable-detail', id] })
    queryClient.invalidateQueries({ queryKey: ['timetables'] })
  }

  const addSlotMut = useMutation({
    mutationFn: (payload: { course_id: string; faculty_user_id?: string; room?: string; remarks?: string }) =>
      addSlot(id, {
        day_of_week: dialogCell!.day,
        period_number: dialogCell!.period,
        ...payload,
      }),
    onSuccess: () => {
      setDialogCell(null)
      setError(null)
      invalidate()
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  const deleteSlotMut = useMutation({
    mutationFn: (slot: TimetableSlot) => deleteSlot(id, slot.id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  const submitMut = useMutation({
    mutationFn: () => submitTimetable(id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  if (isError) {
    return (
      <div className="space-y-4">
        <button onClick={onBack} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
          <ChevronLeft className="h-4 w-4" /> Back to timetables
        </button>
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load this timetable. Please go back and try again.
        </div>
      </div>
    )
  }

  if (isLoading || !data) {
    return <div className="h-64 rounded-xl bg-gray-50 animate-pulse" />
  }

  const editable = data.status === 'DRAFT' || data.status === 'REJECTED'

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
        <ChevronLeft className="h-4 w-4" /> Back to timetables
      </button>

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">{timetableLabel(data)}</h2>
          <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[data.status] ?? 'bg-gray-100 text-gray-600'}`}>
            {data.status.replace('_', ' ')}
          </span>
          {!data.template && (
            <span className="ml-2 text-[11px] text-gray-400">No template linked — using default periods.</span>
          )}
        </div>
        {editable && data.slots.length > 0 && (
          <Button disabled={submitMut.isPending} onClick={() => submitMut.mutate()}>
            {submitMut.isPending ? 'Submitting…' : 'Submit for Review'}
          </Button>
        )}
      </div>

      {data.status === 'REJECTED' && data.review_comment && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          <strong>Rejected:</strong> {data.review_comment}
        </div>
      )}
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{error}</div>
      )}

      <TimetableGrid
        slots={data.slots}
        periods={data.template?.periods}
        workingDays={data.template?.working_days}
        saturdayMode={data.template?.saturday_mode}
        editable={editable}
        onAddSlot={editable ? (day, period) => setDialogCell({ day, period }) : undefined}
        onDeleteSlot={editable ? (slot) => deleteSlotMut.mutate(slot) : undefined}
      />

      {dialogCell && (
        <AddSlotDialog
          open={!!dialogCell}
          onOpenChange={(v) => !v && setDialogCell(null)}
          semesterId={data.semester_id}
          sectionId={data.section_id}
          dayOfWeek={dialogCell.day}
          periodNumber={dialogCell.period}
          onSubmit={(p) => addSlotMut.mutate(p)}
          isSubmitting={addSlotMut.isPending}
          error={error}
        />
      )}
    </div>
  )
}

function CreateTimetableDialog({
  open, onOpenChange, onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: (id: string) => void
}) {
  const queryClient = useQueryClient()
  const [semesterId, setSemesterId] = useState('')
  const [sectionId, setSectionId] = useState('')
  const [templateId, setTemplateId] = useState('')
  const [error, setError] = useState<string | null>(null)

  const semestersQ = useQuery({ queryKey: ['semesters-all'], queryFn: () => academicsApi.listSemesters() })
  const sectionsQ = useQuery({
    queryKey: ['sections', semesterId],
    queryFn: () => academicsApi.listSections(semesterId),
    enabled: !!semesterId,
  })
  const templatesQ = useQuery({ queryKey: ['timetable-templates'], queryFn: () => listTemplates() })

  const createMut = useMutation({
    mutationFn: () => createTimetable({
      section_id: sectionId,
      semester_id: semesterId,
      template_id: templateId || undefined,
    }),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: ['timetables'] })
      onOpenChange(false)
      setSemesterId('')
      setSectionId('')
      setTemplateId('')
      setError(null)
      // Jump straight into the grid instead of leaving the Dean on the plain
      // list view — the created timetable already has its full template
      // (working days/periods/breaks) loaded server-side.
      onCreated(created.id)
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Create Timetable</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-gray-500 mb-1">Semester</label>
            <Select value={semesterId} onValueChange={(v) => { setSemesterId(v); setSectionId('') }}>
              <SelectTrigger><SelectValue placeholder="Select semester" /></SelectTrigger>
              <SelectContent>
                {(semestersQ.data ?? []).map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.program_name ?? 'Program'} — Sem {s.number} {s.label ? `(${s.label})` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Section</label>
            <Select value={sectionId} onValueChange={setSectionId} disabled={!semesterId}>
              <SelectTrigger><SelectValue placeholder="Select section" /></SelectTrigger>
              <SelectContent>
                {(sectionsQ.data ?? []).map((s) => (
                  <SelectItem key={s.id} value={s.id}>Section {s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Template (optional)</label>
            <Select value={templateId} onValueChange={setTemplateId}>
              <SelectTrigger><SelectValue placeholder="No template — use default periods" /></SelectTrigger>
              <SelectContent>
                {(templatesQ.data ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.name} ({t.department_name})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!semesterId || !sectionId || createMut.isPending} onClick={() => createMut.mutate()}>
            {createMut.isPending ? 'Creating…' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function TimetableListSection({
  title, items, isLoading, isError, emptyIcon: EmptyIcon, emptyMessage, onSelect,
}: {
  title?: string
  items: TimetableListItem[]
  isLoading: boolean
  isError?: boolean
  emptyIcon: typeof CalendarClock
  emptyMessage: string
  onSelect: (id: string) => void
}) {
  return (
    <div className="space-y-3">
      {title && <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h3>}
      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load timetables. Please refresh.
        </div>
      )}
      {isLoading ? (
        <div className="space-y-3">{[1, 2].map((n) => <div key={n} className="h-14 rounded-xl bg-gray-50 animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <EmptyIcon className="h-10 w-10 mx-auto mb-3 text-gray-300" />
          <p className="text-sm text-gray-500">{emptyMessage}</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((t) => (
            <button
              key={t.id}
              onClick={() => onSelect(t.id)}
              className="w-full flex items-center justify-between gap-4 px-5 py-4 hover:bg-gray-50 transition-colors text-left"
            >
              <span className="text-sm font-semibold text-gray-800">{timetableLabel(t)}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[t.status] ?? 'bg-gray-100 text-gray-600'}`}>
                {t.status.replace('_', ' ')}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Draft Timetables — DRAFT (being built) + REJECTED (needs fixing, resubmit)
// ---------------------------------------------------------------------------

function DraftTimetablesTab() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const draftQ = useQuery({
    queryKey: ['timetables', 'DRAFT'],
    queryFn: () => listTimetables({ status: 'DRAFT' }),
    enabled: !selectedId,
  })
  const rejectedQ = useQuery({
    queryKey: ['timetables', 'REJECTED'],
    queryFn: () => listTimetables({ status: 'REJECTED' }),
    enabled: !selectedId,
  })

  if (selectedId) {
    return <TimetableDetail id={selectedId} onBack={() => setSelectedId(null)} />
  }

  const items = [...(draftQ.data ?? []), ...(rejectedQ.data ?? [])]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-gray-500">Create and manage class timetables per section.</p>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-1" /> Create Timetable
        </Button>
      </div>

      <TimetableListSection
        items={items}
        isLoading={draftQ.isLoading || rejectedQ.isLoading}
        isError={draftQ.isError || rejectedQ.isError}
        emptyIcon={CalendarClock}
        emptyMessage="No draft timetables yet."
        onSelect={setSelectedId}
      />

      <CreateTimetableDialog open={creating} onOpenChange={setCreating} onCreated={setSelectedId} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Pending Review — Dean approves/rejects timetables submitted for review
// ---------------------------------------------------------------------------

function PendingReviewRow({ item }: { item: TimetableListItem }) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [comment, setComment] = useState('')
  const [error, setError] = useState<string | null>(null)

  const detailQ = useQuery({
    queryKey: ['timetable-detail', item.id],
    queryFn: () => getTimetable(item.id),
    enabled: expanded,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['timetables'] })
    queryClient.invalidateQueries({ queryKey: ['timetable-detail', item.id] })
  }

  const approveMut = useMutation({
    mutationFn: () => approveTimetable(item.id),
    onSuccess: invalidate,
    onError: (e) => setError(getErrorMessage(e)),
  })

  const rejectMut = useMutation({
    mutationFn: () => rejectTimetable(item.id, comment),
    onSuccess: () => {
      setRejecting(false)
      setComment('')
      invalidate()
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  return (
    <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between gap-4 px-5 py-4 hover:bg-gray-50 transition-colors"
      >
        <div className="text-left">
          <p className="text-sm font-semibold text-gray-800">{timetableLabel(item)}</p>
          <p className="text-xs text-gray-500">Submitted {item.submitted_at ? new Date(item.submitted_at).toLocaleString() : '—'}</p>
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
      </button>

      {expanded && (
        <div className="px-5 pb-5 space-y-4 border-t border-gray-100 pt-4">
          {detailQ.isLoading ? (
            <div className="h-48 rounded-xl bg-gray-50 animate-pulse" />
          ) : detailQ.data ? (
            <TimetableGrid
              slots={detailQ.data.slots}
              periods={detailQ.data.template?.periods}
              workingDays={detailQ.data.template?.working_days}
              saturdayMode={detailQ.data.template?.saturday_mode}
              editable={false}
            />
          ) : null}

          {error && <div className="text-xs text-red-600">{error}</div>}

          {rejecting ? (
            <div className="space-y-2">
              <Textarea
                placeholder="Reason for rejection…"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                rows={3}
              />
              <div className="flex gap-2 justify-end">
                <Button size="sm" variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button>
                <Button
                  size="sm"
                  variant="destructive"
                  disabled={!comment.trim() || rejectMut.isPending}
                  onClick={() => rejectMut.mutate()}
                >
                  {rejectMut.isPending ? 'Rejecting…' : 'Confirm Reject'}
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2 justify-end">
              <Button size="sm" variant="outline" onClick={() => setRejecting(true)}>Reject</Button>
              <Button size="sm" disabled={approveMut.isPending} onClick={() => approveMut.mutate()}>
                {approveMut.isPending ? 'Approving…' : 'Approve'}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PendingReviewTab() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['pending-timetables'],
    queryFn: listPendingTimetables,
  })

  const items = data ?? []

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500">Approve or reject timetables submitted for review.</p>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load pending timetables. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2].map((n) => <div key={n} className="h-16 rounded-xl bg-gray-50 animate-pulse" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <ClipboardCheck className="h-10 w-10 mx-auto mb-3 text-gray-300" />
          <p className="text-sm text-gray-500">No timetables are pending review.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => <PendingReviewRow key={item.id} item={item} />)}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Published — APPROVED (ready to publish) + PUBLISHED (live)
// ---------------------------------------------------------------------------

function PublishedTimetablesTab() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const approvedQ = useQuery({
    queryKey: ['timetables', 'APPROVED'],
    queryFn: () => listTimetables({ status: 'APPROVED' }),
    enabled: !selectedId,
  })
  const publishedQ = useQuery({
    queryKey: ['timetables', 'PUBLISHED'],
    queryFn: () => listTimetables({ status: 'PUBLISHED' }),
    enabled: !selectedId,
  })

  const publishMut = useMutation({
    mutationFn: (id: string) => publishTimetable(id),
    onSuccess: () => {
      setError(null)
      queryClient.invalidateQueries({ queryKey: ['timetables'] })
    },
    onError: (e) => setError(getErrorMessage(e)),
  })

  if (selectedId) {
    return <TimetableDetail id={selectedId} onBack={() => setSelectedId(null)} />
  }

  const approvedItems = approvedQ.data ?? []
  const publishedItems = publishedQ.data ?? []

  return (
    <div className="space-y-6">
      {error && <div className="text-xs text-red-600">{error}</div>}

      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Ready to Publish</h3>
        {approvedQ.isLoading ? (
          <div className="h-14 rounded-xl bg-gray-50 animate-pulse" />
        ) : approvedItems.length === 0 ? (
          <p className="text-sm text-gray-500">No approved timetables waiting to publish.</p>
        ) : (
          <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
            {approvedItems.map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-4 px-5 py-4">
                <button onClick={() => setSelectedId(t.id)} className="text-sm font-semibold text-gray-800 hover:underline text-left">
                  {timetableLabel(t)}
                </button>
                <Button size="sm" disabled={publishMut.isPending} onClick={() => publishMut.mutate(t.id)}>
                  <Rocket className="h-3.5 w-3.5 mr-1.5" /> Publish
                </Button>
              </div>
            ))}
          </div>
        )}
      </div>

      <TimetableListSection
        title="Published"
        items={publishedItems}
        isLoading={publishedQ.isLoading}
        isError={publishedQ.isError}
        emptyIcon={CalendarClock}
        emptyMessage="No published timetables yet."
        onSelect={setSelectedId}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Archive — superseded / past-semester timetables (no dedicated status yet)
// ---------------------------------------------------------------------------

function ArchiveTimetablesTab() {
  return (
    <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
      <Archive className="h-10 w-10 mx-auto mb-3 text-gray-300" />
      <p className="text-sm text-gray-500">Superseded and past-semester timetables will appear here.</p>
    </div>
  )
}

export default function TimetableBuilderPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Timetable</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Configure your academic schedule, then create, review, and publish section timetables.
        </p>
      </div>

      <Tabs defaultValue="draft">
        <TabsList>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          <TabsTrigger value="draft">Draft Timetables</TabsTrigger>
          <TabsTrigger value="pending">Pending Review</TabsTrigger>
          <TabsTrigger value="published">Published</TabsTrigger>
          <TabsTrigger value="archive">Archive</TabsTrigger>
        </TabsList>
        <TabsContent value="templates"><TemplatesTab /></TabsContent>
        <TabsContent value="draft"><DraftTimetablesTab /></TabsContent>
        <TabsContent value="pending"><PendingReviewTab /></TabsContent>
        <TabsContent value="published"><PublishedTimetablesTab /></TabsContent>
        <TabsContent value="archive"><ArchiveTimetablesTab /></TabsContent>
      </Tabs>
    </div>
  )
}
