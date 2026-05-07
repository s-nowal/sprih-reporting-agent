/**
 * Base HTTP client for the FastAPI backend.
 *
 * Centralises the BASE_URL prefix, JSON helpers, and the auth-header hook
 * so individual endpoint modules (threads, runs, …) stay short.
 */

import { BASE_URL } from './config'

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, body: unknown, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

/** Phase 4 will read a JWT from localStorage; for now this is a no-op. */
function authHeader(): Record<string, string> {
  const token = localStorage.getItem('sprih.authToken')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** JSON request → JSON response. Throws ApiError on non-2xx. */
export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...authHeader(),
      ...(init.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null)
    throw new ApiError(res.status, body, `${res.status} ${res.statusText}`)
  }
  // 204 has no body
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** POST that returns a streaming SSE Response. Caller consumes res.body. */
export async function apiStream(
  path: string,
  body: unknown,
  init: RequestInit = {},
): Promise<Response> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...authHeader(),
      ...(init.headers ?? {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text, `${res.status} ${res.statusText}`)
  }
  return res
}
