import api from '@/lib/api'

export interface School {
  id: string
  code: string
  name: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string | null
}

export const sisApi = {
  listSchools: (includeInactive = false) =>
    api.get<School[]>('/sis/schools', { params: { include_inactive: includeInactive } }).then(r => r.data),

  getSchool: (id: string) =>
    api.get<School>(`/sis/schools/${id}`).then(r => r.data),

  createSchool: (body: { code: string; name: string; description?: string }) =>
    api.post<School>('/sis/schools', body).then(r => r.data),

  updateSchool: (id: string, body: Partial<{ code: string; name: string; description: string; is_active: boolean }>) =>
    api.put<School>(`/sis/schools/${id}`, body).then(r => r.data),

  deleteSchool: (id: string) =>
    api.delete(`/sis/schools/${id}`).then(r => r.data),
}
