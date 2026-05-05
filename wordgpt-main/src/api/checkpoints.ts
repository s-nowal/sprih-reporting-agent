import type { RunnableConfig } from '@langchain/core/runnables'
import { BaseCheckpointSaver, Checkpoint, CheckpointMetadata, type CheckpointTuple } from '@langchain/langgraph'
export type { CheckpointTuple }

export interface Thread {
  id: string
  title: string
  createdAt: Date
  updatedAt: Date
}

export interface CheckpointListOptions {
  limit?: number
  before?: RunnableConfig
}

import { BASE_URL } from './config'

export class IndexedDBSaver extends BaseCheckpointSaver {
  constructor() {
    super()
  }

  private _buildTuple(
    thread_id: string,
    checkpoint_id: string,
    values: Record<string, any>,
    ts?: string,
    step = 0,
  ): CheckpointTuple {
    const checkpoint: Checkpoint = {
      v: 1,
      ts: ts ?? new Date().toISOString(),
      id: checkpoint_id,
      channel_values: values,
      channel_versions: {},
      versions_seen: {},
    }
    return {
      config: { configurable: { thread_id, checkpoint_id } },
      checkpoint,
      metadata: { source: 'input', step, parents: {} } as CheckpointMetadata,
    }
  }

  async getTuple(config: RunnableConfig): Promise<CheckpointTuple | undefined> {
    const thread_id = config.configurable?.thread_id
    if (!thread_id) return undefined

    try {
      const res = await fetch(`${BASE_URL}/threads/${thread_id}/state`)
      if (!res.ok) return undefined
      const state = await res.json()
      const values = state.values ?? {}
      const checkpoint_id = config.configurable?.checkpoint_id ?? `state-${thread_id}`
      return this._buildTuple(thread_id, checkpoint_id, values)
    } catch (err) {
      console.error('[ApiSaver] getTuple error:', err)
      return undefined
    }
  }

  async *list(config: RunnableConfig, options?: CheckpointListOptions): AsyncGenerator<CheckpointTuple> {
    const thread_id = config.configurable?.thread_id

    try {
      if (thread_id) {
        // History for a specific thread
        const res = await fetch(`${BASE_URL}/threads/${thread_id}/history`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        })

        if (res.ok) {
          const history: any[] = await res.json()
          if (history.length) {
            let step = history.length
            for (const item of history) {
              const cp_id = item.checkpoint_id ?? item.id ?? `hist-${thread_id}-${step}`
              yield this._buildTuple(
                thread_id,
                cp_id,
                item.values ?? item.checkpoint?.channel_values ?? {},
                item.created_at,
                step--,
              )
            }
            return
          }
        }

        // Backend history not yet populated — fall back to current state
        const tuple = await this.getTuple(config)
        if (tuple) yield tuple
      } else {
        // List all threads (used by checkPointsPage session list)
        const limit = options?.limit ?? 50
        const res = await fetch(`${BASE_URL}/threads/search`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ limit }),
        })
        if (!res.ok) return

        const threads: any[] = await res.json()
        for (const thread of threads) {
          const tId = thread.thread_id ?? thread.id
          if (!tId) continue
          try {
            const stateRes = await fetch(`${BASE_URL}/threads/${tId}/state`)
            if (!stateRes.ok) continue
            const state = await stateRes.json()
            const ts = thread.updated_at ?? thread.created_at ?? new Date().toISOString()
            yield this._buildTuple(tId, `state-${tId}`, state.values ?? {}, ts)
          } catch {
            continue
          }
        }
      }
    } catch (err) {
      console.error('[ApiSaver] list error:', err)
    }
  }

  async put(config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata): Promise<RunnableConfig> {
    // Backend manages state via runs — no local storage needed
    const thread_id = config.configurable?.thread_id ?? ''
    const checkpoint_id = checkpoint.id ?? crypto.randomUUID()
    return { configurable: { thread_id, checkpoint_id } }
  }

  async putWrites(_config: RunnableConfig, _writes: [string, any][], _taskId: string): Promise<void> {
    // no-op
  }

  async deleteCheckpoint(_threadId: string, _checkpointId: string): Promise<void> {
    // no-op: no per-checkpoint delete endpoint
  }

  async deleteThread(threadId: string): Promise<void> {
    if (!threadId) return
    try {
      await fetch(`${BASE_URL}/threads/${threadId}`, { method: 'DELETE' })
    } catch (err) {
      console.error('[ApiSaver] deleteThread error:', err)
      throw err
    }
  }
}
