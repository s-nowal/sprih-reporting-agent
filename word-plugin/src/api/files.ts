/**
 * Thread-scoped file manager client.
 *
 * Wraps the single ``/threads/{tid}/files`` endpoint, with the operation
 * chosen by HTTP verb + query parameter:
 *
 *   list     → GET    ?prefix=...
 *   read     → GET    ?path=...
 *   write    → PUT    ?path=...      body {content}
 *   upload   → POST   ?folder=...    multipart
 *   delete   → DELETE ?path=...
 *
 * All paths returned by the backend are *thread-relative* (no
 * thread-id prefix) so callers can present them in chat suffixes
 * without leaking the storage layout.
 */

import { ApiError, apiJson } from './client'
import { BASE_URL } from './config'

export interface FileObject {
  key: string
  size: number
  modified_at: string
}

export interface FileContent {
  key: string
  content: string
  size: number
}

export interface WriteResult {
  key: string
  size: number
}

/** Convention: paperclip drops land here. */
export const UPLOAD_FOLDER = 'input/userUpload'
/** Convention: shared sync canvas lives here. */
export const SYNC_PATH = 'output/output.md'

function authHeader(): Record<string, string> {
  const token = localStorage.getItem('sprih.authToken')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function base(threadId: string): string {
  return `/threads/${encodeURIComponent(threadId)}/files`
}

/** List files under ``prefix`` (empty string = thread root). */
export async function listFiles(
  threadId: string,
  prefix: string = '',
): Promise<FileObject[]> {
  const params = new URLSearchParams()
  if (prefix) params.set('prefix', prefix)
  const qs = params.toString() ? `?${params}` : ''
  return apiJson<FileObject[]>(`${base(threadId)}${qs}`)
}

/** Read one file as UTF-8 text. */
export async function readFile(
  threadId: string,
  path: string,
): Promise<FileContent> {
  const params = new URLSearchParams({ path })
  return apiJson<FileContent>(`${base(threadId)}?${params}`)
}

/** Write or replace one file from a text body. */
export async function writeFile(
  threadId: string,
  path: string,
  content: string,
): Promise<WriteResult> {
  const params = new URLSearchParams({ path })
  return apiJson<WriteResult>(`${base(threadId)}?${params}`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

/** Multipart batch upload into ``folder``. */
export async function uploadFiles(
  threadId: string,
  files: File[],
  folder: string = UPLOAD_FOLDER,
): Promise<WriteResult[]> {
  if (files.length === 0) return []

  const form = new FormData()
  for (const f of files) form.append('files', f, f.name)

  // Do NOT set Content-Type — the browser fills in the multipart boundary.
  const params = new URLSearchParams({ folder })
  const res = await fetch(`${BASE_URL}${base(threadId)}?${params}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      ...authHeader(),
    },
    body: form,
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text, `${res.status} ${res.statusText}`)
  }
  return (await res.json()) as WriteResult[]
}

/** Delete one file. */
export async function deleteFile(threadId: string, path: string): Promise<void> {
  const params = new URLSearchParams({ path })
  await apiJson<void>(`${base(threadId)}?${params}`, { method: 'DELETE' })
}
