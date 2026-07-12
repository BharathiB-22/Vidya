import api from '@/lib/api'

const BASE = '/electives'

/** One interchangeable choice inside a slot — a real subject with its own code,
 *  credits and faculty. `registered_count` is demand, not capacity: Phase 5 has
 *  no seat limit, so a choice is never "full". */
export interface ElectiveOption {
  course_id: string
  code: string
  title: string
  credits: number
  course_type: string | null
  description: string | null
  faculty_user_id: string | null
  faculty_name: string | null
  registered_count: number
}

export type ElectiveSlotStatus = 'DRAFT' | 'PUBLISHED' | 'OPEN' | 'CLOSED'

/** One curriculum elective slot the student must satisfy this semester, e.g.
 *  "Elective 1 (3 credits)". The slot comes straight from the published
 *  program — there is no separate offering to open. */
export interface ElectiveSlot {
  basket_id: string
  name: string
  description: string | null
  credits: number
  semester: number
  semester_id: string
  status: ElectiveSlotStatus
  /** True only while the slot is OPEN. PUBLISHED = visible but not yet
   *  registerable; CLOSED = frozen. */
  can_register: boolean
  options: ElectiveOption[]
  /** The option this student already picked for this slot, if any. */
  chosen_course_id: string | null
}

/** A slot as the Dean sees it for one running term, each choice carrying the
 *  faculty assigned for that term. Curriculum stays fixed across terms; only
 *  the teaching assignment changes. */
export interface DeanElectiveSlot {
  basket_id: string
  name: string
  description: string | null
  credits: number
  semester: number
  semester_id: string
  status: ElectiveSlotStatus
  options: ElectiveOption[]
}

export async function listElectiveSlotsForTerm(semesterId: string): Promise<DeanElectiveSlot[]> {
  const { data } = await api.get<DeanElectiveSlot[]>(`${BASE}/slots/by-term`, {
    params: { semester_id: semesterId },
  })
  return data
}

export async function assignElectiveChoiceFaculty(
  semesterId: string, courseId: string, facultyUserId: string,
): Promise<void> {
  await api.post(`${BASE}/slots/by-term/${semesterId}/assign-faculty`, {
    course_id: courseId,
    faculty_user_id: facultyUserId,
  })
}

/** Flat registration row — `is_current` (not a server-side current/past grouping)
 * is what distinguishes an active-semester registration from a past one. */
export interface ElectiveRegistration {
  id: string
  basket_id: string
  basket_name: string
  course_id: string
  course_code: string
  course_title: string
  credits: number
  semester_id: string
  semester_label: string | null
  status: 'REGISTERED' | 'DROPPED'
  registered_at: string
  is_current: boolean
}

// ---------------------------------------------------------------------------
// Faculty — the combined elective class (one subject, every section that chose it)
// ---------------------------------------------------------------------------

export interface ElectiveRosterStudent {
  student_id: string
  student_name: string
  usn: string | null
  student_email: string | null
  section_name: string | null
  registered_at: string
}

export interface FacultyElectiveRoster {
  course_id: string
  course_code: string
  course_title: string
  basket_id: string
  semester_id: string
  semester_label: string | null
  basket_name: string
  total_students: number
  /** How many sections this combined class draws from (MCA-A + MCA-B -> 2). */
  section_count: number
  students: ElectiveRosterStudent[]
}

export async function getFacultyElectiveRoster(): Promise<FacultyElectiveRoster[]> {
  const { data } = await api.get<FacultyElectiveRoster[]>(`${BASE}/faculty/roster`)
  return data
}

// ---------------------------------------------------------------------------
// Student — this semester's slots, choose one option per slot, drop
// ---------------------------------------------------------------------------

/** The slots for the student's own current semester. The server derives the
 *  semester from their active enrollment, so no semester id is passed. */
export async function getMyElectiveSlots(): Promise<ElectiveSlot[]> {
  const { data } = await api.get<ElectiveSlot[]>(`${BASE}/slots`)
  return data
}

export async function registerElective(basketId: string, courseId: string): Promise<ElectiveRegistration> {
  const { data } = await api.post<ElectiveRegistration>(`${BASE}/slots/${basketId}/register`, {
    course_id: courseId,
  })
  return data
}

export async function dropElective(basketId: string): Promise<ElectiveRegistration> {
  const { data } = await api.post<ElectiveRegistration>(`${BASE}/slots/${basketId}/drop`)
  return data
}

/** Flat list of the student's registrations — derive current/past client-side via `is_current`. */
export async function getMyElectives(): Promise<ElectiveRegistration[]> {
  const { data } = await api.get<ElectiveRegistration[]>(`${BASE}/me`)
  return data
}
