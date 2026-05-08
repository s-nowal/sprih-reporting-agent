/**
 * Thread CRUD calls to the FastAPI Agent Protocol endpoints.
 *
 * A thread is the conversation; the backend's checkpointer keys all state
 * by `thread_id`. We persist the id in localStorage so a tab refresh
 * resumes the same conversation.
 */

import { apiJson } from './client'

export type MessageType = 'human' | 'ai' | 'tool' | 'system'

export interface AgentMessage {
  type: MessageType
  id: string
  content: string
  tool_calls?: Array<{ id: string; name: string; args: Record<string, unknown> }>
  tool_call_id?: string
  name?: string
}

export interface ThreadResponse {
  thread_id: string
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
  status: 'idle' | 'busy' | 'interrupted' | 'error'
  values: { messages?: AgentMessage[] } & Record<string, unknown>
  interrupts: Record<string, unknown[]>
}

export interface ThreadState {
  values: { messages?: AgentMessage[] } & Record<string, unknown>
  next: string[]
  checkpoint: unknown
}

export async function createThread(
  metadata?: Record<string, unknown>,
): Promise<ThreadResponse> {
  return apiJson<ThreadResponse>('/threads', {
    method: 'POST',
    body: JSON.stringify({ metadata: metadata ?? null }),
  })
}

export async function getThreadState(threadId: string): Promise<ThreadState> {
  return apiJson<ThreadState>(`/threads/${threadId}/state`)
}

export interface ThreadSummary {
  thread_id: string
  title: string | null
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

/** Maximum length of an auto-derived title (from the first human message). */
const AUTO_TITLE_MAX = 60

/** Derive a display title for a thread.
 *
 * Priority: explicit ``metadata.title`` → first human message in
 * ``values.messages`` (collapsed whitespace, truncated). Returns
 * ``null`` if neither is available so the caller can show its own
 * fallback (typically the thread id prefix).
 */
function deriveTitle(t: ThreadResponse): string | null {
  const explicit = t.metadata?.title
  if (typeof explicit === 'string' && explicit.trim()) return explicit
  const messages = (t.values as { messages?: AgentMessage[] })?.messages
  if (!messages?.length) return null
  const firstHuman = messages.find((m) => m.type === 'human')
  if (!firstHuman) return null
  const raw =
    typeof firstHuman.content === 'string'
      ? firstHuman.content
      : ''
  const collapsed = raw.replace(/\s+/g, ' ').trim()
  if (!collapsed) return null
  return collapsed.length > AUTO_TITLE_MAX
    ? collapsed.slice(0, AUTO_TITLE_MAX - 1) + '…'
    : collapsed
}

/** List the caller's threads, most recently updated first.
 *
 * Uses ``POST /threads/search`` (the Agent Protocol shape — query
 * params via JSON body). Display title falls back through
 * ``metadata.title`` → first human message excerpt → ``null`` (UI
 * shows the id prefix as a last resort).
 */
export async function listThreads(limit = 50): Promise<ThreadSummary[]> {
  const raw = await apiJson<ThreadResponse[]>('/threads/search', {
    method: 'POST',
    body: JSON.stringify({ limit, offset: 0 }),
  })
  return raw.map((t) => ({
    thread_id: t.thread_id,
    title: deriveTitle(t),
    created_at: t.created_at,
    updated_at: t.updated_at,
    metadata: t.metadata,
  }))
}
