import api from '@/lib/api'

const BASE = '/electives'

export interface ElectiveOffering {
  id: string
  course_id: string
  course_code: string
  course_title: string
  description: string | null
  credits: number
  faculty_user_id: string | null
  faculty_name: string | null
  semester_id: string
  max_seats: number
  seats_taken: number
  registration_opens_at: string | null
  registration_closes_at: string | null
  status: 'OPEN' | 'CLOSED'
}

export interface ElectiveRegistration {
  id: string
  offering_id: string
  course_code: string
  course_title: string
  semester_id: string
  status: 'REGISTERED' | 'DROPPED' | 'WAITLISTED'
  registered_at: string
}

export interface MyElectivesResponse {
  current: ElectiveRegistration[]
  past: ElectiveRegistration[]
}

export async function listElectiveOfferings(semesterId: string): Promise<ElectiveOffering[]> {
  const { data } = await api.get<ElectiveOffering[]>(`${BASE}/offerings`, {
    params: { semester_id: semesterId },
  })
  return data
}

export async function registerElective(offeringId: string): Promise<ElectiveRegistration> {
  const { data } = await api.post<ElectiveRegistration>(`${BASE}/offerings/${offeringId}/register`)
  return data
}

export async function dropElective(offeringId: string): Promise<ElectiveRegistration> {
  const { data } = await api.post<ElectiveRegistration>(`${BASE}/offerings/${offeringId}/drop`)
  return data
}

export async function getMyElectives(): Promise<MyElectivesResponse> {
  const { data } = await api.get<MyElectivesResponse>(`${BASE}/me`)
  return data
}
