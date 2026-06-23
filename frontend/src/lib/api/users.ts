import api from '@/lib/api'

export interface UserRecord {
  id: string
  email: string
  role: string
  full_name: string
  identifier: string | null
  acad_program_id: string | null
  acad_program_name: string | null
  is_active: boolean
  created_at: string
  grants?: string[]
}

export interface CreateUserPayload {
  email: string
  password: string
  full_name: string
  role: string
  identifier?: string
  acad_program_id?: string
  department_id?: string
}

export interface UpdateUserPayload {
  full_name?: string
  role?: string
  is_active?: boolean
  identifier?: string
  email?: string
  acad_program_id?: string
  department_id?: string
}

export interface AcademicOverviewEntry {
  program_id: string
  program_name: string
  program_code: string
  degree_type: string
  is_active: boolean
  student_count: number
  faculty_count: number
  section_count: number
}

export const usersApi = {
  list: (programId?: string): Promise<UserRecord[]> =>
    api.get('/admin/users', { params: programId ? { program_id: programId } : {} }).then((r) => r.data),

  create: (payload: CreateUserPayload): Promise<UserRecord> =>
    api.post('/admin/users', payload).then((r) => r.data),

  update: (userId: string, payload: UpdateUserPayload): Promise<UserRecord> =>
    api.patch(`/admin/users/${userId}`, payload).then((r) => r.data),

  academicOverview: (): Promise<AcademicOverviewEntry[]> =>
    api.get('/admin/academic-overview').then((r) => r.data),
}
