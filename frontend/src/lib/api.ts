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
    const url = err.config?.url ?? ''
    // Auth endpoints handle 401 themselves — don't redirect from login/refresh/change-password
    const isAuthEndpoint = url.includes('/auth/login') || url.includes('/auth/refresh') ||
      url.includes('/auth/change-password') || url.includes('/auth/password-reset')
    if (err.response?.status === 401 && !isAuthEndpoint) {
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
  const axiosErr = err as AxiosError<BackendError & { detail?: BackendError | string | unknown[] }>
  const data = axiosErr.response?.data
  // Custom HTTPException handler returns exc.detail directly: { error, message }
  if (data && typeof data === 'object' && typeof (data as BackendError).message === 'string') {
    return (data as BackendError).message
  }
  // FastAPI default wraps in detail
  const detail = (data as { detail?: BackendError | string | unknown[] })?.detail
  if (detail && typeof detail === 'object' && !Array.isArray(detail) && 'message' in detail) {
    return (detail as BackendError).message
  }
  // FastAPI 422 Pydantic validation errors: {detail: [{msg, loc, type}]}
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string }
    if (typeof first?.msg === 'string') {
      return first.msg.replace(/^Value error,\s*/i, '')
    }
  }
  if (typeof detail === 'string') return detail
  return 'An unexpected error occurred.'
}

export default api