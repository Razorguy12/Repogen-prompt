const TOKEN_KEY = 'token'

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem('user_name')
  sessionStorage.removeItem('is_admin')
}

export const SESSION_EXPIRED_KEY = 'session_expired'

export function expireSession(): void {
  clearToken()
  sessionStorage.setItem(SESSION_EXPIRED_KEY, '1')
  window.location.assign('/login')
}

export class ApiError extends Error {
  status: number
  /** Structured `detail` from the API when it is an object (e.g. duplicate-patient matches). */
  detail?: unknown

  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }

  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json'
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(path, { ...options, headers })

  if (!response.ok) {
    if (response.status === 401 && token && path !== '/api/token') expireSession()
    let message = `Request failed (${response.status})`
    let detail: unknown
    try {
      const data = await response.json()
      detail = data.detail
      message = data.detail || data.message || message
      if (message && typeof message === 'object' && !Array.isArray(message)) {
        message = (message as { message?: string }).message || `Request failed (${response.status})`
      }
      if (Array.isArray(message)) {
        message = message.map((e: { msg?: string }) => e.msg || String(e)).join(', ')
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, String(message), detail)
  }

  if (response.status === 204) {
    return undefined as T
  }

  const contentType = response.headers.get('content-type')
  if (contentType?.includes('application/json')) {
    return response.json()
  }

  return response as unknown as T
}

export async function apiFetchBlob(
  path: string,
  options: RequestInit = {},
): Promise<Blob> {
  const token = getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(path, { ...options, headers })
  if (!response.ok) {
    if (response.status === 401 && token) expireSession()
    throw new ApiError(response.status, 'Download failed')
  }
  return response.blob()
}
