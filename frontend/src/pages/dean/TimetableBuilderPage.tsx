import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarClock, ChevronLeft, Plus, Settings2, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { TimetableGrid } from '@/components/timetable/TimetableGrid'
import { academicsApi } from '@/lib/api/academics'
import { assignmentsApi } from '@/lib/api/assignments'
import {
  listTimetables, createTimetable, getTimetable,
  addSlot, deleteSlot, submitTimetable,
  listTemplates, createTemplate, getTemplate,
  addPeriod, deletePeriod,
} from '@/lib/api/timetable'
import { getErrorMessage } from '@/lib/api'
import {
  DAYS_OF_WEEK, BREAK_PRESETS, formatClockTime,
  type TimetableSlot, type SaturdayMode, type PeriodType,
} from '@/types/timetable'

const STATUS_COLORS: Record<string, string> = {
  DRAFT:           'bg-gray-100 text-gray-600',
  PENDING_REVIEW:  'bg-yellow-50 text-yellow-700',
  APPROVED:        'bg-blue-50 text-blue-700',
  REJECTED:        'bg-red-50 text-red-700',
  PUBLISHED:       'bg-green-50 text-green-700',
}

// ---------------------------------------------------------------------------
// Templates — academic schedule configuration (working days, periods, breaks)
// ---------------------------------------------------------------------------

function CreateTemplateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const queryClient = useQueryClient()
  const [departmentId, setDepartmentId] = useState('')
  const [name, setName] = useState('')
  const [days, setDays] = useState<Set<number>>(new Set([0, 1, 2, 3, 4]))
  const [saturdayMode, setSaturdayMode] = useState<SaturdayMode>('HOLIDAY')
  const [startTime, setStartTime] = useState('08:30')
  const [endTime, setEndTime] = useState('16:00')
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

  const createMut = useMutation({
    mutationFn: () => {
      const workingDays = new Set(days)
      if (saturdayMode === 'HOLIDAY') workingDays.delete(5)
      else workingDays.add(5)
      return createTemplate({
        department_id: departmentId,
        name,
        working_days: [...workingDays].sort(),
        saturday_mode: saturdayMode,
        college_start_time: `${startTime}:00`,
        college_end_time: `${endTime}:00`,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timetable-templates'] })
      onOpenChange(false)
      setName(''); setDepartmentId(''); setError(null)
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
          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!canSubmit || createMut.isPending} onClick={() => createMut.mutate()}>
            {createMut.isPending ? 'Creating…' : 'Create Template'}
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
        <p className="text-xs text-gray-400 mt-0.5">
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
                <p className="text-xs text-gray-400">
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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['timetable-templates'],
    queryFn: () => listTemplates(),
    enabled: !selectedId,
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
            <button
              key={t.id}
              onClick={() => setSelectedId(t.id)}
              className="w-full flex items-center justify-between gap-4 px-5 py-4 hover:bg-gray-50 transition-colors text-left"
            >
              <div>
                <span className="text-sm font-semibold text-gray-800">{t.name}</span>
                <p className="text-xs text-gray-400">{t.department_name}</p>
              </div>
              <span className="text-xs text-gray-400">{t.periods.length} rows</span>
            </button>
          ))}
        </div>
      )}

      <CreateTemplateDialog open={creating} onOpenChange={setCreating} />
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
  onSubmit: (payload: { course_id: string; faculty_user_id?: string; room?: string }) => void
  isSubmitting: boolean
  error: string | null
}) {
  const [selectedAssignmentIdx, setSelectedAssignmentIdx] = useState<string>('')
  const [room, setRoom] = useState('')

  const assignmentsQ = useQuery({
    queryKey: ['course-assignments-for-timetable', semesterId, sectionId],
    queryFn: () => assignmentsApi.listAll(semesterId, false, sectionId),
    enabled: open,
  })

  const assignments = assignmentsQ.data?.items ?? []

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
            <label className="block text-xs text-gray-500 mb-1">Course / Faculty</label>
            <Select value={selectedAssignmentIdx} onValueChange={setSelectedAssignmentIdx}>
              <SelectTrigger>
                <SelectValue placeholder={assignmentsQ.isLoading ? 'Loading…' : 'Select a course assignment'} />
              </SelectTrigger>
              <SelectContent>
                {assignments.map((a, idx) => (
                  <SelectItem key={a.id} value={String(idx)}>
                    {a.course?.code ?? 'Course'} — {a.faculty?.full_name ?? 'Unassigned faculty'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!assignmentsQ.isLoading && assignments.length === 0 && (
              <p className="text-xs text-gray-400 mt-1">
                No faculty are assigned to courses in this section/semester yet.
              </p>
            )}
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Room (optional)</label>
            <Input value={room} onChange={(e) => setRoom(e.target.value)} placeholder="e.g. Block A, Room 204" />
          </div>

          {error && <p className="text-xs text-red-600">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={!selectedAssignmentIdx || isSubmitting}
            onClick={() => {
              const a = assignments[Number(selectedAssignmentIdx)]
              if (!a?.course_id) return
              onSubmit({ course_id: a.course_id, faculty_user_id: a.faculty_user_id, room: room || undefined })
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

  const { data, isLoading } = useQuery({
    queryKey: ['timetable-detail', id],
    queryFn: () => getTimetable(id),
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['timetable-detail', id] })
    queryClient.invalidateQueries({ queryKey: ['timetables'] })
  }

  const addSlotMut = useMutation({
    mutationFn: (payload: { course_id: string; faculty_user_id?: string; room?: string }) =>
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
          <h2 className="text-lg font-semibold text-gray-900">Section {data.section_name}</h2>
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

function CreateTimetableDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['timetables'] })
      onOpenChange(false)
      setSemesterId('')
      setSectionId('')
      setTemplateId('')
      setError(null)
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

function TimetablesTab() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['timetables'],
    queryFn: () => listTimetables(),
    enabled: !selectedId,
  })

  if (selectedId) {
    return <TimetableDetail id={selectedId} onBack={() => setSelectedId(null)} />
  }

  const items = data ?? []

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm text-gray-400">Create and manage class timetables per section.</p>
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-4 w-4 mr-1" /> Create Timetable
        </Button>
      </div>

      {isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to load timetables. Please refresh.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-3">{[1, 2].map((n) => <div key={n} className="h-14 rounded-xl bg-gray-50 animate-pulse" />)}</div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 rounded-xl border border-dashed border-gray-200">
          <CalendarClock className="h-10 w-10 mx-auto mb-3 text-gray-200" />
          <p className="text-sm text-gray-400">No timetables created yet.</p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 divide-y divide-gray-100 bg-white overflow-hidden">
          {items.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelectedId(t.id)}
              className="w-full flex items-center justify-between gap-4 px-5 py-4 hover:bg-gray-50 transition-colors text-left"
            >
              <span className="text-sm font-semibold text-gray-800">Section {t.section_name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[t.status] ?? 'bg-gray-100 text-gray-600'}`}>
                {t.status.replace('_', ' ')}
              </span>
            </button>
          ))}
        </div>
      )}

      <CreateTimetableDialog open={creating} onOpenChange={setCreating} />
    </div>
  )
}

export default function TimetableBuilderPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Timetable Builder</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Configure your academic schedule, then create and manage section timetables.
        </p>
      </div>

      <Tabs defaultValue="timetables">
        <TabsList>
          <TabsTrigger value="templates">Templates</TabsTrigger>
          <TabsTrigger value="timetables">Timetables</TabsTrigger>
        </TabsList>
        <TabsContent value="templates"><TemplatesTab /></TabsContent>
        <TabsContent value="timetables"><TimetablesTab /></TabsContent>
      </Tabs>
    </div>
  )
}
