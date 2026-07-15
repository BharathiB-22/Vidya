export type TimetableStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED' | 'REJECTED' | 'PUBLISHED'
export type SaturdayMode = 'FULL' | 'HALF' | 'HOLIDAY'
export type PeriodType = 'PERIOD' | 'BREAK'

export interface TimetablePeriod {
  id: string
  sequence_number: number
  period_type: PeriodType
  period_number: number | null
  label: string | null
  start_time: string
  end_time: string
  skip_on_half_day: boolean
}

export interface TimetableTemplate {
  id: string
  department_id: string
  department_name: string
  name: string
  working_days: number[]
  saturday_mode: SaturdayMode | null
  college_start_time: string
  college_end_time: string
  periods: TimetablePeriod[]
  created_by_user_id: string
  created_at: string
  updated_at: string
}

/** Lightweight row returned by the templates LIST endpoint — it carries a
 *  `period_count` scalar instead of the full `periods` array (which only the
 *  detail endpoint embeds). */
export interface TimetableTemplateListItem {
  id: string
  department_id: string
  department_name: string
  name: string
  working_days: number[]
  saturday_mode: SaturdayMode | null
  college_start_time: string
  college_end_time: string
  period_count: number
  created_by_user_id: string
  created_at: string
  updated_at: string | null
}

export interface TimetableSlot {
  id: string
  day_of_week: number
  period_number: number
  course_id: string
  course_code: string
  course_title: string
  faculty_user_id: string | null
  faculty_name: string | null
  room: string | null
  remarks: string | null
  /** True when the course is an elective choice, which is taught as one combined
   *  class across every section that chose it. The cell badges this and never
   *  names a section; scheduling the combined class is a later phase. */
  is_elective: boolean
  start_time: string | null
  end_time: string | null
  period_label: string | null
  /** Not persisted yet. Locks live in the workspace's session state; the grid
   *  reads `slot.is_locked ?? localLocks.has(slot.id)` so that the day a column
   *  exists, only the source of truth changes. */
  is_locked?: boolean
}

export interface FacultyTimetableSlot extends TimetableSlot {
  section_name: string
  semester_name: string
  program_name: string | null
}

export interface Timetable {
  id: string
  section_id: string
  section_name: string
  semester_id: string
  semester_label: string | null
  program_name: string | null
  /** Short programme code, e.g. "MCA". */
  program_code: string | null
  /** The batch this section belongs to, e.g. "2026–2028". Two live admissions of
   *  the same programme are told apart by this and nothing else. */
  academic_year: string | null
  status: TimetableStatus
  slots: TimetableSlot[]
  template_id: string | null
  template: TimetableTemplate | null
  created_by_user_id: string
  submitted_at: string | null
  reviewed_by_user_id: string | null
  reviewed_at: string | null
  review_comment: string | null
  published_by_user_id: string | null
  published_at: string | null
  created_at: string
  updated_at: string
}

export interface TimetableListItem extends Omit<Timetable, 'slots' | 'template'> {
  slots?: TimetableSlot[]
  template?: TimetableTemplate | null
}

export interface StudentTimetable {
  section_id: string
  section_name: string
  semester_label: string | null
  program_name: string | null
  academic_year: string | null
  slots: TimetableSlot[]
  template: TimetableTemplate | null
}

export interface FacultyTimetable {
  slots: FacultyTimetableSlot[]
}

export interface CreateTimetablePayload {
  section_id: string
  semester_id: string
  template_id?: string
}

export interface AddSlotPayload {
  day_of_week: number
  period_number: number
  course_id: string
  faculty_user_id?: string
  room?: string
  remarks?: string
}

/** Move a slot (day/period) or edit it in place. Only what is sent changes; the
 *  server validates the resulting position, so a rejected move leaves the entry
 *  exactly where it was. */
export interface UpdateSlotPayload {
  day_of_week?: number
  period_number?: number
  faculty_user_id?: string | null
  room?: string | null
  remarks?: string | null
}

export interface SwapSlotsPayload {
  slot_a_id: string
  slot_b_id: string
}

/** `template_id: null` detaches the template and falls back to Period 1..8. */
export interface UpdateTimetablePayload {
  template_id: string | null
}

export interface CreateTemplatePayload {
  department_id: string
  name: string
  working_days: number[]
  saturday_mode?: SaturdayMode | null
  college_start_time: string
  college_end_time: string
}

export interface UpdateTemplatePayload {
  name?: string
  working_days?: number[]
  saturday_mode?: SaturdayMode | null
  college_start_time?: string
  college_end_time?: string
}

export interface CreatePeriodPayload {
  sequence_number: number
  period_type: PeriodType
  period_number?: number | null
  label?: string | null
  start_time: string
  end_time: string
  skip_on_half_day?: boolean
}

export interface UpdatePeriodPayload {
  sequence_number?: number
  period_type?: PeriodType
  period_number?: number | null
  label?: string | null
  start_time?: string
  end_time?: string
  skip_on_half_day?: boolean
}

export const DAYS_OF_WEEK = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export const BREAK_PRESETS = ['Tea Break', 'Lunch Break', 'Prayer Break', 'Department Meeting']

/** Strips seconds from an "HH:MM:SS" time string for display (e.g. "08:30:00" -> "8:30"). */
export function formatClockTime(time: string): string {
  const [h, m] = time.split(':')
  const hourNum = Number(h)
  return `${hourNum}:${m}`
}
