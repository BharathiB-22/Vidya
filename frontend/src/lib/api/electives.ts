import api from '@/lib/api'

const BASE = '/electives'

export type ElectiveOfferingStatus = 'PROPOSED' | 'DEAN_APPROVED' | 'REJECTED' | 'OPEN' | 'CLOSED'

export interface OfferingCourse {
  course_id: string
  code: string
  title: string
  credits: number
  description: string | null
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
  proposed_by_user_id?: string | null
  approved_by_user_id?: string | null
  approved_at?: string | null
  published_by_user_id?: string | null
  published_at?: string | null
  rejection_reason?: string | null
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
  faculty_name: string | null
}

export interface EligibleElectiveBasket {
  basket_id: string
  name: string
  description: string | null
  courses: EligibleBasketCourse[]
  already_offered: boolean
}

export async function listEligibleElectiveBaskets(semesterId: string): Promise<EligibleElectiveBasket[]> {
  const { data } = await api.get<EligibleElectiveBasket[]>(`${BASE}/eligible-baskets`, {
    params: { semester_id: semesterId },
  })
  return data
}

export interface ElectiveOfferingProposePayload {
  basket_id: string
  semester_id: string
  max_seats: number
  registration_opens_at?: string
  registration_closes_at?: string
}

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

// ---------------------------------------------------------------------------
// Elective offering workflow — Faculty proposes → Dean approves → Dean publishes
// ---------------------------------------------------------------------------

export async function proposeElective(payload: ElectiveOfferingProposePayload): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings/propose`, payload)
  return data
}

export async function getMyProposedElectives(): Promise<ElectiveOffering[]> {
  const { data } = await api.get<ElectiveOffering[]>(`${BASE}/offerings/mine`)
  return data
}

export async function getPendingElectiveApprovals(): Promise<ElectiveOffering[]> {
  const { data } = await api.get<ElectiveOffering[]>(`${BASE}/offerings/pending`)
  return data
}

export async function approveElective(offeringId: string): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings/${offeringId}/approve`)
  return data
}

export async function rejectElective(offeringId: string, reason: string): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings/${offeringId}/reject`, { reason })
  return data
}

export async function getApprovedElectives(): Promise<ElectiveOffering[]> {
  const { data } = await api.get<ElectiveOffering[]>(`${BASE}/offerings/approved`)
  return data
}

export async function publishElective(offeringId: string): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings/${offeringId}/publish`)
  return data
}

// Direct create — existing DEAN shortcut, unchanged behavior (status defaults to OPEN).
export interface ElectiveOfferingCreatePayload {
  basket_id: string
  semester_id: string
  max_seats: number
  registration_opens_at?: string
  registration_closes_at?: string
}

export async function createElectiveOffering(payload: ElectiveOfferingCreatePayload): Promise<ElectiveOffering> {
  const { data } = await api.post<ElectiveOffering>(`${BASE}/offerings`, payload)
  return data
}
