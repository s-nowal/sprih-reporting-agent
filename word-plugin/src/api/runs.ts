/**
 * Streaming run client.
 *
 * The backend's POST /threads/{id}/runs/stream returns an SSE response
 * with frames in the order: metadata → N × values → (error?) → end.
 *
 * Browsers' built-in EventSource only supports GET, so we use fetch +
 * ReadableStream and parse SSE frames manually.
 *
 * Each `values` payload contains the FULL message list (the agent
 * resends the whole state on every step). Consumers should REPLACE,
 * not append.
 */

import { apiStream } from './client'
import type { AgentMessage } from './threads'

export type RunEvent =
  | { event: 'metadata'; data: { run_id: string; thread_id: string } }
  | { event: 'values'; data: { messages: AgentMessage[] } }
  | { event: 'error'; data: { error: string; message: string } }
  | { event: 'end'; data: null }

export interface StreamRunOptions {
  threadId: string
  message: string
  assistantId?: string
  clientType?: 'browser' | 'word'
  signal?: AbortSignal
}

export async function* streamRun(
  opts: StreamRunOptions,
): AsyncGenerator<RunEvent, void, void> {
  const body = {
    assistant_id: opts.assistantId ?? 'reporting-agent',
    input: { messages: [{ type: 'human', content: opts.message }] },
    stream_mode: 'values',
    config: { client_type: opts.clientType ?? 'browser' },
  }

  const res = await apiStream(
    `/threads/${opts.threadId}/runs/stream`,
    body,
    { signal: opts.signal },
  )

  if (!res.body) throw new Error('No response body for SSE stream')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      // sse-starlette emits CRLF; normalise so the frame scan is uniform.
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

      // SSE frames are separated by a blank line (\n\n).
      let sep = buffer.indexOf('\n\n')
      while (sep !== -1) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const evt = parseFrame(frame)
        if (evt) yield evt
        sep = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parseFrame(frame: string): RunEvent | null {
  let event = ''
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    // ignore comments (`:`) and other SSE fields
  }
  if (!event) return null
  const raw = dataLines.join('\n')
  if (raw === 'null' || raw === '') {
    return { event, data: null } as RunEvent
  }
  try {
    return { event, data: JSON.parse(raw) } as RunEvent
  } catch (e) {
    console.warn('SSE: failed to parse data for event', event, raw, e)
    return null
  }
}
