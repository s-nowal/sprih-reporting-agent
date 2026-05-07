<template>
  <div class="flex h-screen flex-col bg-bg">
    <!-- header -->
    <header
      class="flex shrink-0 items-center justify-between border-b border-border bg-bg-secondary px-4 py-3"
    >
      <div class="flex flex-col">
        <h1 class="text-base font-semibold text-main">Sprih Reporting Agent</h1>
        <span class="text-xs text-tertiary">
          {{ threadId ? `thread ${threadId.slice(0, 8)}…` : 'new conversation' }}
        </span>
      </div>
      <button
        class="cursor-pointer rounded-md px-2 py-1 text-xs text-secondary hover:bg-bg-tertiary hover:text-main disabled:opacity-50"
        :disabled="streaming"
        @click="newChat"
      >
        New chat
      </button>
    </header>

    <!-- messages -->
    <div ref="scrollEl" class="flex-1 overflow-y-auto p-4">
      <div
        v-if="!displayMessages.length"
        class="mt-12 text-center text-sm text-tertiary"
      >
        Send a message to start.
      </div>
      <div class="flex flex-col gap-3">
        <div
          v-for="m in displayMessages"
          :key="m.id"
          :class="bubbleClass(m)"
        >
          <div class="mb-1 text-[10px] uppercase tracking-wider text-tertiary">
            {{ m.type }}
          </div>
          <div class="whitespace-pre-wrap text-sm text-main">{{ m.content }}</div>
          <div
            v-if="m.tool_calls?.length"
            class="mt-2 space-y-1 text-xs text-secondary"
          >
            <div v-for="tc in m.tool_calls" :key="tc.id">
              → <span class="font-mono">{{ tc.name }}</span
              >({{ briefArgs(tc.args) }})
            </div>
          </div>
        </div>
      </div>
      <div v-if="streaming" class="mt-3 text-xs italic text-tertiary">
        agent is thinking…
      </div>
      <div v-if="error" class="mt-3 text-sm text-danger">{{ error }}</div>
    </div>

    <!-- input -->
    <form
      class="flex shrink-0 gap-2 border-t border-border bg-bg-secondary p-3"
      @submit.prevent="onSubmit"
    >
      <input
        v-model="input"
        :disabled="streaming"
        type="text"
        placeholder="Ask the agent…"
        class="flex-1 rounded-md border border-border bg-bg px-3 py-2 text-sm text-main outline-none focus:border-accent disabled:opacity-50"
      />
      <button
        type="submit"
        :disabled="streaming || !input.trim()"
        class="cursor-pointer rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        Send
      </button>
    </form>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onMounted, ref } from 'vue'

import { streamRun } from '@/api/runs'
import { createThread, getThreadState, type AgentMessage } from '@/api/threads'

const THREAD_KEY = 'sprih.threadId'

const threadId = ref<string | null>(localStorage.getItem(THREAD_KEY))
const messages = ref<AgentMessage[]>([])
const input = ref('')
const streaming = ref(false)
const error = ref<string | null>(null)
const scrollEl = ref<HTMLElement | null>(null)

const displayMessages = computed(() =>
  messages.value.filter((m) => {
    if (m.type === 'human') return true
    if (m.type === 'ai') return !!m.content || !!m.tool_calls?.length
    return false
  }),
)

function bubbleClass(m: AgentMessage): string {
  const base = 'max-w-[85%] rounded-lg p-3 shadow-sm'
  return m.type === 'human'
    ? `${base} ml-auto bg-accent/10`
    : `${base} mr-auto bg-bg-secondary`
}

function briefArgs(args: Record<string, unknown>): string {
  const s = JSON.stringify(args)
  return s.length > 60 ? s.slice(0, 57) + '…' : s
}

async function ensureThread(): Promise<string> {
  if (threadId.value) return threadId.value
  const t = await createThread({ source: 'word-plugin' })
  threadId.value = t.thread_id
  localStorage.setItem(THREAD_KEY, t.thread_id)
  return t.thread_id
}

async function hydrate() {
  if (!threadId.value) return
  try {
    const state = await getThreadState(threadId.value)
    messages.value = state.values.messages ?? []
    scrollToBottom()
  } catch (e) {
    // Stale thread id from a wiped backend → drop and start fresh
    console.warn('Hydrate failed, resetting thread:', e)
    localStorage.removeItem(THREAD_KEY)
    threadId.value = null
  }
}

async function onSubmit() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  input.value = ''
  error.value = null
  streaming.value = true

  // Optimistic: show the user's message immediately.
  // Backend will resend the full list (including this) on the first
  // `values` event, replacing this placeholder.
  messages.value = [
    ...messages.value,
    { type: 'human', id: `user-${Date.now()}`, content: text },
  ]
  scrollToBottom()

  try {
    const tid = await ensureThread()
    for await (const evt of streamRun({ threadId: tid, message: text })) {
      if (evt.event === 'values') {
        messages.value = evt.data.messages
        scrollToBottom()
      } else if (evt.event === 'error') {
        error.value = `${evt.data.error}: ${evt.data.message}`
      }
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    streaming.value = false
  }
}

function newChat() {
  localStorage.removeItem(THREAD_KEY)
  threadId.value = null
  messages.value = []
  error.value = null
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

onMounted(hydrate)
</script>
