import api from '@/lib/api'

const BASE = '/electives'

export type ElectiveOfferingStatus = 'OPEN' | 'CLOSED'

export interface OfferingCourse {
  course_id: string
  code: string
  title: string
  credits: number
  description: string | null
  faculty_user_id: string | null
  faculty_name: string | null
  seats_taken: number
}

export interface ElectiveOffering {
  id: string
  basket_id: string
  basket_name: string
  basket_description: string | null
  semester_id: string
  max_seats: number
  courses: OfferingCourse[]
  registration_opens_at: string | null
  registration_closes_at: string | null
  status: ElectiveOfferingStatus
  created_at: string
}

/** Flat registration row — `is_current` (not a server-side current/past grouping)
 * is what distinguishes an active-semester registration from a past one. */
export interface ElectiveRegistration {
  id: string
  offering_id: string
  basket_id: string
  basket_name: string
  course_id: string
  course_code: string
  course_title: string
  credits: number
  semester_id: string
  semester_label: string | null
  status: 'REGISTERED' | 'DROPPED' | 'WAITLISTED'
  registered_at: string
  is_current: boolean
}

export interface EligibleBasketCourse {
  course_id: string
  code: string
  title: string
  credits: number
  description: string | null
  faculty_user_id: string | null
  faculty_name: string | null
}

export interface EligibleElectiveBasket {
  basket_id: string
  name: string
  description: string | null
  courses: EligibleBasketCourse[]
  already_offered: boolean
}

// ---------------------------------------------------------------------------
// Dean — offering lifecycle (create with faculty, assign faculty, edit, stats)
// ---------------------------------------------------------------------------

export async function listEligibleElectiveBaskets(semesterId: string): Promise<EligibleElectiveBasket[]> {
  const { data } = await api.get<EligibleElectiveBasket[]>(`${BASE}/eligible-baskets`, {
    params: { semester_id: semesterId },
  })
  return data
}

export interface OfferingFacultyAssignment {
  course_id: string
  faculty_user_id: string
}

export interface ElectiveOfferingCreatePayload {
  basket_id: string
  semester_id: string
  max_seats: number
  faculty_assignments?: OfferingFacultyAssignment[]
  registration_opens_at?: string
  registration_closes_at?: string
}

export async function createElectiveOffering(payload: ElectiveOfferingCreatePayload): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings`, payload)
  return data
}

export async function assignElectiveFaculty(
  offeringId: string, courseId: string, facultyUserId: string,
): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings/${offeringId}/assign-faculty`, {
    course_id: courseId,
    faculty_user_id: facultyUserId,
  })
  return data
}

export interface ElectiveOfferingUpdatePayload {
  max_seats?: number
  status?: ElectiveOfferingStatus
  registration_opens_at?: string
  registration_closes_at?: string
}

export async function updateElectiveOffering(
  offeringId: string, payload: ElectiveOfferingUpdatePayload,
): Promise<ElectiveOffering> {
  const { data } = await api.patch<ElectiveOffering>(`${BASE}/offerings/${offeringId}`, payload)
  return data
}

export interface DeanElectiveDashboard {
  total_offerings: number
  total_registrations: number
  offerings: ElectiveOffering[]
}

export async function getDeanElectiveDashboard(semesterId?: string): Promise<DeanElectiveDashboard> {
  const { data } = await api.get<DeanElectiveDashboard>(`${BASE}/dashboard`, {
    params: semesterId ? { semester_id: semesterId } : undefined,
  })
  return data
}

// ---------------------------------------------------------------------------
// Faculty — read-only roster of students who chose their elective(s)
// ---------------------------------------------------------------------------

export interface ElectiveRosterStudent {
  student_id: string
  student_name: string
  usn: string | null
  student_email: string | null
  registered_at: string
}

export interface FacultyElectiveRoster {
  course_id: string
  course_code: string
  course_title: string
  offering_id: string
  semester_id: string
  semester_label: string | null
  basket_name: string
  total_students: number
  students: ElectiveRosterStudent[]
}

export async function getFacultyElectiveRoster(): Promise<FacultyElectiveRoster[]> {
  const { data } = await api.get<FacultyElectiveRoster[]>(`${BASE}/faculty/roster`)
  return data
}

// ---------------------------------------------------------------------------
// Student — available electives + register / drop / my electives
// ---------------------------------------------------------------------------

export async function listElectiveOfferings(semesterId: string): Promise<ElectiveOffering[]> {
  const { data } = await api.get<ElectiveOffering[]>(`${BASE}/offerings`, {
    params: { semester_id: semesterId },
  })
  return data
}

export async function registerElective(offeringId: string, courseId: string): Promise<ElectiveRegistration> {
  const { data } = await api.post<ElectiveRegistration>(`${BASE}/offerings/${offeringId}/register`, {
    course_id: courseId,
  })
  return data
}

export async function dropElective(offeringId: string): Promise<ElectiveRegistration> {
  const { data } = await api.post<ElectiveRegistration>(`${BASE}/offerings/${offeringId}/drop`)
  return data
}

/** Flat list of the student's registrations — derive current/past client-side via `is_current`. */
export async function getMyElectives(): Promise<ElectiveRegistration[]> {
  const { data } = await api.get<ElectiveRegistration[]>(`${BASE}/me`)
  return data
}
