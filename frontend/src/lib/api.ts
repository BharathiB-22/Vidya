import axios, { type AxiosError } from 'axios'

export interface BackendError {
  error: string
  message: string
}

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

function getStoredToken(): string | null {
  const directToken = localStorage.getItem('vidya_token')
  if (directToken) return directToken

  const auth = localStorage.getItem('vidya_auth')
  if (!auth) return null

  try {
    const parsed = JSON.parse(auth)
    return parsed.access_token ?? null
  } catch {
    return null
  }
}

api.interceptors.request.use((config) => {
  const token = getStoredToken()
  const slug = localStorage.getItem('vidya_tenant_slug')

  if (token) config.headers.Authorization = `Bearer ${token}`
  if (slug) config.headers['X-Tenant-Slug'] = slug

  return config
})

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ detail: BackendError | string }>) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('vidya_token')
      localStorage.removeItem('vidya_auth')
      localStorage.removeItem('vidya_refresh_token')
      localStorage.removeItem('vidya_role')
      // Keep vidya_tenant_slug so the login form pre-fills with the institution.
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export function getErrorMessage(err: unknown): string {
  const axiosErr = err as AxiosError<{ detail: BackendError | string }>
  const detail = axiosErr.response?.data?.detail
  if (detail && typeof detail === 'object' && 'message' in detail) return detail.message
  if (typeof detail === 'string') return detail
  return 'An unexpected error occurred.'
}

export default api