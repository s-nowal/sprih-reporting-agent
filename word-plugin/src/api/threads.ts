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
