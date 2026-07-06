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
  start_time: string | null
  end_time: string | null
  period_label: string | null
}

export interface FacultyTimetableSlot extends TimetableSlot {
  section_name: string
  semester_name: string
}

export interface Timetable {
  id: string
  section_id: string
  section_name: string
  semester_id: string
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
