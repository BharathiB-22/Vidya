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
  // The active workspace is the server-enforced viewing context: a Dean in the
  // Faculty workspace is scoped exactly as Faculty. The backend validates this
  // against the user's entitled roles, so it can only ever re-select among roles
  // the user already holds — never elevate. Written by WorkspaceProvider.
  const workspace = localStorage.getItem('vidya_active_workspace')

  if (token) config.headers.Authorization = `Bearer ${token}`
  if (slug) config.headers['X-Tenant-Slug'] = slug
  if (workspace) config.headers['X-Active-Workspace'] = workspace

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
      localStorage.removeItem('vidya_active_workspace')
      // Keep vidya_tenant_slug so the login form pre-fills with the institution.
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export function getErrorMessage(err: unknown): string {
  const axiosErr = err as AxiosError<BackendError & { detail?: BackendError | string | unknown[] }>
  const status = axiosErr.response?.status
  const data   = axiosErr.response?.data

  // 500 / server errors — never expose internal stack traces to the user
  if (!status || status >= 500) {
    return 'The server encountered an error. Please try again in a moment.'
  }

  // Network / no response
  if (!data) {
    return 'Unable to reach the server. Check your connection and try again.'
  }

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