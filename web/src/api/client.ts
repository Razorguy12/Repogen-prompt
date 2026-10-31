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

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
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
    try {
      const data = await response.json()
      message = data.detail || data.message || message
      if (Array.isArray(message)) {
        message = message.map((e: { msg?: string }) => e.msg || String(e)).join(', ')
      }
    } catch {
      // ignore parse errors
    }
    throw new ApiError(response.status, String(message))
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
