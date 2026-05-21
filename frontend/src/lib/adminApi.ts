import axios, { type AxiosError } from 'axios'
import type { BackendError } from '@/lib/api'

// Separate axios instance for Super Admin (platform-level) endpoints.
// Uses the same /api proxy as the main api client but attaches the
// platform admin token instead of a tenant token, and never sends
// X-Tenant-Slug since platform routes are tenant-agnostic.
const adminApi = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

adminApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('vidya_admin_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

adminApi.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ detail: BackendError | string }>) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('vidya_admin_token')
      window.location.href = '/admin/login'
    }
    return Promise.reject(err)
  },
)

export function getAdminErrorMessage(err: unknown): string {
  const axiosErr = err as AxiosError<{ detail: BackendError | string }>
  const detail = axiosErr.response?.data?.detail
  if (detail && typeof detail === 'object' && 'message' in detail) return detail.message
  if (typeof detail === 'string') return detail
  return 'An unexpected error occurred.'
}

export default adminApi
