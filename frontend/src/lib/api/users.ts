import api from '@/lib/api'

export interface UserRecord {
  id: string
  email: string
  role: string
  full_name: string
  identifier: string | null
  is_active: boolean
  created_at: string
}

export interface CreateUserPayload {
  email: string
  password: string
  full_name: string
  role: string
  identifier?: string
}

export interface UpdateUserPayload {
  full_name?: string
  role?: string
  is_active?: boolean
  identifier?: string
}

export const usersApi = {
  list: (): Promise<UserRecord[]> =>
    api.get('/admin/users').then((r) => r.data),

  create: (payload: CreateUserPayload): Promise<UserRecord> =>
    api.post('/admin/users', payload).then((r) => r.data),

  update: (userId: string, payload: UpdateUserPayload): Promise<UserRecord> =>
    api.patch(`/admin/users/${userId}`, payload).then((r) => r.data),
}
