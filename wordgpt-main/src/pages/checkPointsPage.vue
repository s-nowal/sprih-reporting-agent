<template>
  <div
    class="relative flex h-full w-full flex-col bg-[#0b0d10] p-2 text-[#ffffff]"
    style="font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; font-size: 13px;"
  >
    <div class="relative flex h-full w-full flex-col gap-1 rounded-md">
      <!-- Header -->
      <div class="flex items-center gap-1 rounded-sm border border-[#ffffff]/5 bg-[#13161b] px-1.5 py-1">
        <button
          class="flex h-6 w-6 items-center justify-center rounded text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
          @click="backToHome"
        >
          <ArrowLeft :size="13" />
        </button>
        <span class="flex-1 text-[10px] uppercase tracking-wider font-semibold text-[#ffffff]/70">
          {{ t('checkPoints') }}
        </span>
      </div>

      <!-- Content -->
      <div class="flex flex-1 flex-col overflow-hidden rounded-sm border border-[#ffffff]/5 bg-[#0a0c0f]">
        <!-- Loading -->
        <div v-if="loading" class="flex h-full items-center justify-center">
          <div class="flex flex-col items-center gap-2">
            <div class="h-8 w-8 animate-spin rounded-full border-2 border-[#ffffff]/10 border-t-[#00a48a]"></div>
            <span class="text-[10px] text-[#ffffff]/50">{{ t('loading') }}</span>
          </div>
        </div>

        <!-- Empty -->
        <div v-else-if="sessionItems.length === 0" class="flex h-full flex-col items-center justify-center gap-3">
          <PackageIcon :size="28" class="text-[#00a48a]/40" />
          <span class="text-[11px] text-[#ffffff]/50">{{ t('NocheckPoints') }}</span>
        </div>

        <!-- List -->
        <div v-else class="flex h-full w-full flex-col gap-1 overflow-y-auto p-2">
          <div
            v-for="item in sessionItems"
            :key="item.threadId"
            class="group flex cursor-pointer flex-col gap-1.5 rounded-sm border border-[#ffffff]/6 bg-[#13161b] p-2 hover:border-[#00a48a]/40 transition-colors"
            @click="handleSelectSession(item.threadId)"
          >
            <p class="line-clamp-2 text-[11px] leading-relaxed text-[#ffffff]/80 break-all">
              {{ item.previewText }}
            </p>
            <div class="flex items-center justify-between">
              <span class="text-[9px] uppercase tracking-widest text-[#ffffff]/40">
                {{ formatTime(item.timestamp) }}
              </span>
              <div class="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  class="flex h-5 w-5 items-center justify-center rounded text-[#ffffff]/60 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
                  :title="t('detail')"
                  @click.stop="handleSelectSession(item.threadId)"
                >
                  <SquareMousePointer :size="11" />
                </button>
                <button
                  class="flex h-5 w-5 items-center justify-center rounded text-[#ffffff]/60 hover:bg-[#00a48a]/20 hover:text-[#00a48a] transition-colors"
                  :title="t('copyToClipboard')"
                  @click.stop="copyItemPrompt(item.previewText)"
                >
                  <Copy :size="11" />
                </button>
                <button
                  class="flex h-5 w-5 items-center justify-center rounded text-[#ffffff]/60 hover:bg-red-500/20 hover:text-red-400 transition-colors"
                  :title="t('delete')"
                  @click.stop="deleteSession(item.threadId)"
                >
                  <Delete :size="11" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { RunnableConfig } from '@langchain/core/runnables'
import { ArrowLeft, Copy, Delete, PackageIcon, SquareMousePointer } from 'lucide-vue-next'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { IndexedDBSaver } from '@/api/checkpoints'
import { message as messageUtil } from '@/utils/message'

const props = defineProps<{
  threadId?: string
  saver: IndexedDBSaver
  currentCheckpointId?: string // 当前正在显示的节点 ID
}>()

const emit = defineEmits<{
  (e: 'select-thread', threadId: string): void
  (e: 'restore', checkpointId: string): void
  (e: 'close'): void
}>()

const { t } = useI18n()

interface SessionViewItem {
  threadId: string
  timestamp: string
  previewText: string
  messageCount: number
  toolName?: string
}

const sessionItems = ref<SessionViewItem[]>([])
const loading = ref(false)

const formatTime = (isoStr: string) => {
  try {
    const date = new Date(isoStr)
    return date.toLocaleString(undefined, {
      month: 'numeric',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch (e) {
    console.error('Failed to format time:', e)
    return isoStr
  }
}

const loadAllSessions = async () => {
  loading.value = true
  sessionItems.value = []

  const sessionMap = new Map<string, SessionViewItem>()
  try {
    const config: RunnableConfig = {
      configurable: {},
    }

    const iterator = props.saver.list(config, { limit: 50 })

    for await (const tuple of iterator) {
      const { checkpoint, config } = tuple

      const tId = config.configurable?.thread_id
      if (!tId) continue

      const existing = sessionMap.get(tId)
      const currentTs = checkpoint.ts
      if (existing && new Date(existing.timestamp) >= new Date(currentTs)) {
        continue
      }

      interface CheckpointMessage {
        _getType: () => 'ai' | 'human' | 'tool'
        content: string | any
        tool_calls?: { name: string }[]
      }

      const messages = (checkpoint.channel_values?.messages || []) as CheckpointMessage[]
      const lastMsg = messages.at(-1)

      if (!lastMsg) continue
      let previewText = '[Complex Content]'
      if (typeof lastMsg.content === 'string') {
        previewText = lastMsg.content
      } else if (Array.isArray(lastMsg.content)) {
        previewText = lastMsg.content.map((c: any) => c.text || '').join(' ')
      }

      previewText = previewText.slice(0, 100) + (previewText.length > 100 ? '...' : '')
      if (!previewText) previewText = '[Empty Message]'

      sessionMap.set(tId, {
        threadId: tId,
        timestamp: currentTs,
        previewText: previewText || '[Empty Session]',
        messageCount: messages.length,
        toolName: lastMsg.tool_calls?.length ? lastMsg.tool_calls[0].name : undefined,
      })
    }
    sessionItems.value = Array.from(sessionMap.values()).sort((a, b) => {
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    })
  } catch (err) {
    console.error('Failed to load sessions:', err)
  } finally {
    loading.value = false
  }
}

const handleSelectSession = (threadId: string) => {
  emit('select-thread', threadId)
}

const deleteSession = async (threadId: string) => {
  try {
    await props.saver.deleteThread(threadId)
    sessionItems.value = sessionItems.value.filter(item => item.threadId !== threadId)
    messageUtil.success(t('deleteSuccess'))
  } catch (error) {
    console.error('Failed to delete session:', error)
    messageUtil.error(t('deleteFailed'))
  }
}

const copyItemPrompt = (text: string) => {
  if (!text) return
  navigator.clipboard.writeText(text)
  messageUtil.success(t('copied'))
}

onMounted(() => {
  loadAllSessions()
})

function backToHome() {
  emit('close')
}
</script>
