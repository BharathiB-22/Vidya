import api from '@/lib/api'

const BASE = '/calendar'

/** Every dated academic thing a student must know about, in one vocabulary.
 *
 *  The first groups are DECLARED (academic_events); the last is AGGREGATED at
 *  query time from whichever module owns the deadline. A student does not care
 *  which is which — the calendar shows them side by side. */
export type CalendarItemType =
  // Declared — non-teaching days
  | 'HOLIDAY'
  | 'GOVERNMENT_HOLIDAY'
  | 'UNIVERSITY_HOLIDAY'
  // Declared — things that happen
  | 'EVENT'
  | 'DEPARTMENT_EVENT'
  | 'ANNOUNCEMENT'
  // Declared — dated assessment
  | 'INTERNAL_ASSESSMENT'
  | 'QUIZ'
  | 'LAB_EXAM'
  | 'PROJECT_REVIEW'
  | 'RESEARCH_MILESTONE'
  | 'SUBMISSION_DEADLINE'
  // Declared — the student's own note
  | 'PERSONAL'
  | 'OTHER'
  // Aggregated from the owning module
  | 'ASSIGNMENT_DUE'
  | 'LAB_DUE'
  | 'EXAM'
  | 'VIVA'

export interface CalendarItem {
  id: string
  title: string
  /** One line of context — course code, room, exam session. */
  detail: string | null
  item_type: CalendarItemType
  date: string
  start_time: string | null
  end_time: string | null
  all_day: boolean
  source_module: 'calendar' | 'assignments' | 'labs' | 'exam' | 'research'
  link: string | null
  /** True only for the student's own personal notes — the only items here that
   *  are theirs to remove. */
  editable: boolean
}

export interface PersonalEventCreate {
  title: string
  description?: string | null
  start_at: string
  end_at?: string | null
  is_all_day?: boolean
}

/** Which weekdays this student actually has class on, 0=Monday .. 6=Sunday.
 *
 *  "Is Saturday a holiday" has no general answer — some institutions teach on
 *  Saturday, some do not — so the calendar reads the student's own published
 *  timetable instead of assuming. */
export async function getMyTeachingDays(): Promise<number[]> {
  const { data } = await api.get<{ teaching_days: number[] }>(`${BASE}/me/teaching-days`)
  return data.teaching_days
}

export async function getMyCalendar(dateFrom: string, dateTo: string): Promise<CalendarItem[]> {
  const { data } = await api.get<CalendarItem[]>(`${BASE}/me`, {
    params: { date_from: dateFrom, date_to: dateTo },
  })
  return data
}

/** Add one's own academic event. Forced to PERSONAL visibility server-side, so
 *  it can never land on anyone else's calendar. */
export async function createMyPersonalEvent(payload: PersonalEventCreate): Promise<void> {
  await api.post(`${BASE}/me/events`, payload)
}

export async function deleteMyPersonalEvent(eventId: string): Promise<void> {
  await api.delete(`${BASE}/me/events/${eventId}`)
}
