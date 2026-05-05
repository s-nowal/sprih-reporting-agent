<template>
  <CheckPointsPage
    v-if="showCheckpoints"
    :thread-id="threadId"
    :saver="saver"
    :current-checkpoint-id="currentCheckpointId"
    @close="showCheckpoints = false"
    @restore="handleRestore"
    @select-thread="handleSelectThread"
  />

  <div
    v-show="!showCheckpoints"
    class="relative flex h-full w-full flex-col bg-[#0b0d10] p-2 text-[#ffffff]"
    style="font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; font-size: 13px;"
  >
    <div class="relative flex h-full w-full flex-col gap-1 rounded-md">
      <div class="flex items-center gap-1 rounded-sm border border-[#ffffff]/5 bg-[#13161b] px-1.5 py-1">
        <div class="relative flex-1" ref="quickActionsRef">
          <button
            class="flex w-full items-center justify-between rounded px-1.5 py-1 text-[10px] text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-all"
            @click="showQuickActions = !showQuickActions"
          >
            <div class="flex items-center gap-1.5">
              <Zap :size="11" class="text-[#00a48a]" />
              <span class="tracking-wider uppercase font-semibold">Quick Actions</span>
            </div>
            <ChevronDown
              :size="11"
              class="transition-transform duration-200"
              :class="{ 'rotate-180': showQuickActions }"
            />
          </button>
        <div
          v-if="showQuickActions"
          class="absolute top-full left-0 right-0 z-20 mt-0.5 rounded-sm border border-[#ffffff]/8 bg-[#13161b] shadow-xl shadow-black/50 overflow-hidden"
        >
          <div class="grid grid-cols-2 gap-px p-1">
            <button
              v-for="action in quickActions"
              :key="action.key"
              class="flex items-center gap-1.5 rounded px-2 py-1.5 text-[10px] text-[#ffffff]/80 hover:bg-[#ffffff]/5 hover:text-[#ffffff] transition-colors text-left disabled:opacity-40 disabled:cursor-not-allowed"
              :disabled="loading"
              :title="action.label"
              @click="applyQuickAction(action.key); showQuickActions = false"
            >
              <component :is="action.icon" :size="11" class="shrink-0 text-[#00a48a]" />
              <span class="truncate">{{ action.label }}</span>
            </button>
          </div>
          <div class="border-t border-[#ffffff]/5 p-1">
            <select
              v-model="selectedPromptId"
              class="w-full rounded bg-[#0d0f12] border border-[#ffffff]/8 px-2 py-1 text-[10px] text-[#ffffff]/70 focus:outline-none focus:border-[#00a48a]/40 cursor-pointer hover:border-[#ffffff]/15 transition-colors"
              @change="loadSelectedPrompt(); showQuickActions = false"
            >
              <option value="" disabled selected>{{ t('selectPrompt') }}</option>
              <option
                v-for="prompt in savedPrompts"
                :key="prompt.id"
                :value="prompt.id"
              >
                {{ prompt.name || prompt.id }}
              </option>
            </select>
          </div>
        </div>
        </div>
        <div class="flex items-center gap-0.5 shrink-0">
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
            :title="t('newChat')"
            @click="startNewChat"
          >
            <Plus :size="13" />
          </button>
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
            :title="t('Outputs')"
            @click="file_system"
          >
            <Files :size="13" />
          </button>
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
            :title="t('settings')"
            @click="settings"
          >
            <Settings :size="13" />
          </button>
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
            :title="t('checkPoints')"
            @click="checkPoints"
          >
            <History :size="13" />
          </button>
        </div>
      </div>
      <div
        ref="messagesContainer"
        class="flex flex-1 flex-col gap-2 overflow-y-auto rounded-sm border border-[#ffffff]/5 bg-[#0a0c0f] p-2 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-[#ffffff]/10"
      >
        <div
          v-if="history.length === 0"
          class="flex h-full flex-col items-center justify-center gap-3 text-center"
        >
          <Sparkles :size="20" class="text-[#00a48a]/40" />
          <p class="text-[11px] font-semibold tracking-wide text-[#ffffff]/60">
            {{ $t('emptyTitle') }}
          </p>
          <p class="text-[10px] text-[#ffffff]/70">
            {{ $t('emptySubtitle') }}
          </p>
        </div>
        <div
          v-for="(msg, index) in displayHistory"
          :key="msg.id || index"
          class="group flex items-end gap-2"
          :class="msg instanceof AIMessage ? 'assistant' : 'user justify-end'"
        >
          <div
            class="flex min-w-0 flex-col gap-0.5"
            :class="msg instanceof AIMessage ? 'items-start max-w-[90%]' : 'items-end max-w-[85%]'"
          >
            <!-- Role label -->
            <span class="px-1 text-[9px] uppercase tracking-widest font-semibold"
              :class="msg instanceof AIMessage ? 'text-[#00a48a]/50' : 'text-[#ffffff]/70'">
              {{ msg instanceof AIMessage ? 'assistant' : 'you' }}
            </span>

            <!-- Bubble -->
            <div
              class="rounded-sm border px-2 py-1.5 text-[11px] leading-relaxed wrap-break-word"
              :class="msg instanceof AIMessage
                ? 'border-[#ffffff]/6 bg-[#13161b] text-[#ffffff]/90'
                : 'border-[#00a48a]/15 bg-[#00a48a]/5 text-[#ffffff] whitespace-pre-wrap'"
            >
              <template v-for="(segment, idx) in renderSegments(msg)" :key="idx">
                <div
                  v-if="segment.type === 'text' && msg instanceof AIMessage"
                  v-html="markdownToHtml(segment.text)"
                  class="ai-markdown"
                />
                <span v-else-if="segment.type === 'text'">{{ segment.text.trim() }}</span>
                <details v-else class="mt-1 rounded border border-[#ffffff]/6 bg-[#0d0f12]">
                  <summary class="cursor-pointer list-none px-2 py-1 text-[9px] uppercase tracking-widest text-[#ffffff]/70 font-semibold">
                    Thought process
                  </summary>
                  <pre class="m-0 px-2 py-1 text-[10px] wrap-break-word whitespace-pre-wrap text-[#ffffff]/70">{{
                    segment.text.trim()
                  }}</pre>
                </details>
              </template>
            </div>

            <!-- AI message actions -->
            <div v-if="msg instanceof AIMessage" class="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                class="flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
                :title="t('replaceSelectedText')"
                @click="insertToDocument(cleanMessageText(msg), 'replace')"
              >
                <FileText :size="9" />
                <span>Replace</span>
              </button>
              <button
                class="flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
                :title="t('appendToSelection')"
                @click="insertToDocument(cleanMessageText(msg), 'append')"
              >
                <Plus :size="9" />
                <span>Append</span>
              </button>
              <button
                class="flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80 transition-colors"
                :title="t('copyToClipboard')"
                @click="copyToClipboard(cleanMessageText(msg))"
              >
                <Copy :size="9" />
                <span>Copy</span>
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="flex flex-col gap-1 rounded-sm border border-[#ffffff]/5 bg-[#13161b] p-1.5">

        <!-- File attachment + sync preview chips -->
        <div
          v-if="(pendingFiles && pendingFiles.length > 0) || new_sync"
          class="flex flex-wrap gap-1 px-1"
        >
          <div
            v-for="(file, idx) in pendingFiles"
            :key="idx"
            class="flex items-center gap-1.5 rounded bg-[#1a1d24] border border-[#ffffff]/10 px-2 py-1 max-w-[160px]"
          >
            <div class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[00a48a]/80">
              <FileText :size="10" class="text-white" />
            </div>
            <div class="flex min-w-0 flex-col leading-tight">
              <span class="truncate text-[9px] font-medium text-[#ffffff]/90 max-w-[100px]">
                {{ file.name }}
              </span>
              <span class="text-[8px] uppercase tracking-wider text-[#ffffff]/40 font-semibold">
                {{ getFileType(file) }}
              </span>
            </div>
            <button
              class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-[#ffffff]/15 text-[#ffffff]/60 hover:bg-[#ffffff]/25 hover:text-[#ffffff] transition-colors ml-0.5"
              @click="removePendingFile(idx)"
            >
              <X :size="8" />
            </button>
          </div>

          <div
            v-if="new_sync"
            class="flex items-center gap-1.5 rounded bg-[#1a1d24] border border-[#ffffff]/10 px-2 py-1 max-w-[160px]"
          >
            <div class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[#00a48a]/80">
              <RefreshCw :size="10" class="text-white" />
            </div>
            <div class="flex min-w-0 flex-col leading-tight">
              <span class="truncate text-[9px] font-medium text-[#ffffff]/90 max-w-[100px]">
                {{ syncFileName || 'Document' }}
              </span>
              <span class="text-[8px] uppercase tracking-wider text-[#ffffff]/40 font-semibold">Sync</span>
            </div>
            <button
              class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-[#ffffff]/15 text-[#ffffff]/60 hover:bg-[#ffffff]/25 hover:text-[#ffffff] transition-colors ml-0.5"
              @click="new_sync = false"
            >
              <X :size="8" />
            </button>
          </div>
        </div>

        <!-- Selected text preview -->
        <div
          v-if="selectedTextPreview"
          class="flex items-start gap-1.5 rounded border border-[#ffffff]/8 bg-[#0d0f12] px-2 py-1.5"
        >
          <CornerDownRight :size="10" class="shrink-0 text-[#ffffff]/30 mt-0.5" />
          <span class="flex-1 truncate text-[10px] text-[#ffffff]/50 italic leading-relaxed">
            "{{ selectedTextPreview }}"
          </span>
          <button
            class="shrink-0 text-[#ffffff]/30 hover:text-[#ffffff]/60 transition-colors"
            @click="dismissSelectedTextPreview()"
          >
            <X :size="9" />
          </button>
        </div>

        <!-- Input row -->
        <div
          class="flex items-end gap-1 rounded border px-2 py-1 transition-colors"
          :class="pendingInterrupt
            ? 'border-amber-400/40 bg-amber-400/5'
            : 'border-[#ffffff]/6 bg-[#0d0f12] focus-within:border-[#00a48a]/30'"
        >
          <div class="relative">
            <button
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#ffffff]/70 hover:text-[#ffffff]/80 hover:bg-[#ffffff]/5 transition-colors disabled:opacity-40"
              :title="t('uploadInput')"
              :disabled="loading"
              @click="showUploadMenu = !showUploadMenu"
            >
              <Upload :size="12" />
            </button>
            <div
              v-if="showUploadMenu"
              class="fixed inset-0 z-40"
              @click="showUploadMenu = false"
            />
            <div
              v-if="showUploadMenu"
              class="absolute bottom-full left-0 mb-1 w-44 rounded border border-[#ffffff]/10 bg-[#13161b] shadow-lg z-50 overflow-hidden"
            >
              <button
                class="flex w-full items-center gap-2 px-3 py-2 text-[10px] text-[#ffffff]/80 hover:bg-[#ffffff]/5 transition-colors"
                @click="() => { showUploadMenu = false; handleAddFilesOrPhotos() }"
              >
                <Paperclip :size="10" />
                Add files or photos
              </button>
            </div>
          </div>

          <textarea
            ref="inputTextarea"
            v-model="userInput"
            :placeholder="pendingInterrupt
              ? `💬 ${interruptMessage}`
              : mode === 'ask' ? $t('askAnything') : $t('directTheAgent')"
            rows="1"
            class="flex-1 resize-none bg-transparent text-[11px] text-[#ffffff] placeholder-[#475569] focus:outline-none leading-relaxed"
            @keydown.enter.exact.prevent="sendMessage"
            @input="adjustTextareaHeight"
          />

          <button
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#ffffff]/70 hover:text-[#ffffff]/80 hover:bg-[#ffffff]/5 transition-colors disabled:opacity-40"
            :title="t('getDocument')"
            :disabled="loading"
            @click="handleGetDocument"
          >
            <CircleArrowLeft :size="12" />
          </button>
          <button
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#ffffff]/70 hover:text-[#ffffff]/80 hover:bg-[#ffffff]/5 transition-colors disabled:opacity-40"
            :title="t('uploadDocument')"
            :disabled="loading"
            @click="handleUploadDocument"
          >
            <CircleArrowRight :size="12" />
          </button>

          <button
            v-if="loading"
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-red-500/80 text-[#ffffff] hover:bg-red-500 transition-colors"
            title="Stop"
            @click="stopGeneration"
          >
            <Square :size="10" />
          </button>
          <button
            v-else
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[#00a48a]/80 text-[#0d0f12] hover:bg-[#00a48a] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Send"
            :disabled="!userInput.trim() && pendingFiles.length === 0 && !selectedTextPreview && !new_sync"
            @click="sendMessage"
          >
            <Send :size="10" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { AIMessage, HumanMessage, Message, SystemMessage } from '@langchain/core/messages'
import { useStorage } from '@vueuse/core'
import {
  BookOpen,
  BotMessageSquare,
  CheckCircle,
  Copy,
  FileCheck,
  FileText,
  Globe,
  History,
  MessageSquare,
  Plus,
  Send,
  Settings,
  Sparkle,
  Sparkles,
  Square,
  Files,
  Download,
  Paperclip,
  CornerDownRight,
  RefreshCw,
  X
} from 'lucide-vue-next'
import { v4 as uuidv4 } from 'uuid'
import { computed, nextTick, onBeforeMount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { uploadCurrentDocument, getCurrentDocument, uploadInputDocument } from '@/api/docreader'
import { CircleArrowLeft, CircleArrowRight, Upload } from 'lucide-vue-next'

import { type CheckpointTuple, IndexedDBSaver } from '@/api/checkpoints'
import { insertFormattedResult, insertResult } from '@/api/common'
import { getAgentResponse, getChatResponse } from '@/api/union'
import CustomButton from '@/components/CustomButton.vue'
import SingleSelect from '@/components/SingleSelect.vue'
import CheckPointsPage from '@/pages/checkPointsPage.vue'
import { checkAuth } from '@/utils/common'
import { buildInPrompt, getBuiltInPrompt } from '@/utils/constant'
import { localStorageKey } from '@/utils/enum'
import { createGeneralTools, GeneralToolName } from '@/utils/generalTools'
import { message as messageUtil } from '@/utils/message'
import useSettingForm from '@/utils/settingForm'
import { settingPreset } from '@/utils/settingPreset'
import { createWordTools, WordToolName } from '@/utils/wordTools'
import { onMounted } from 'vue'

// --- new interrupt state ---
const pendingInterrupt = ref(false)
const interruptMessage = ref('')
const new_sync = ref(false)
const syncFileName = ref<string>('')
const showQuickActions = ref(false)
const quickActionsRef = ref(null)
const selectedTextPreview = ref<string>('')
const dismissedSelectedText = ref<string>('')

// DEBUG ONLY
;(window as any).debugAgent = getAgentResponse
;(window as any).debugChat = getChatResponse
;(window as any).debugProcess = processChat

const router = useRouter()
const { t } = useI18n()

const settingForm = useSettingForm()

interface SavedPrompt {
  id: string
  name: string
  systemPrompt: string
  userPrompt: string
}

const showUploadMenu = ref(false)
const savedPrompts = ref<SavedPrompt[]>([])
const selectedPromptId = ref<string>('')
const customSystemPrompt = ref<string>('')

const allWordToolNames: WordToolName[] = [
  'getSelectedText',
  'getDocumentContent',
  'insertText',
  'replaceSelectedText',
  'appendText',
  'insertParagraph',
  'formatText',
  'searchAndReplace',
  'getDocumentProperties',
  'insertTable',
  'insertList',
  'deleteText',
  'clearFormatting',
  'setFontName',
  'insertPageBreak',
  'getRangeInfo',
  'selectText',
  'insertImage',
  'getTableInfo',
  'insertBookmark',
  'goToBookmark',
  'insertContentControl',
  'findText',
]

const allGeneralToolNames: GeneralToolName[] = ['fetchWebContent', 'searchWeb', 'getCurrentDate', 'calculateMath']
const enabledWordTools = ref<WordToolName[]>(loadEnabledWordTools())
const enabledGeneralTools = ref<GeneralToolName[]>(loadEnabledGeneralTools())
const mode = useStorage(localStorageKey.chatMode, 'agent' as 'ask' | 'agent')
const history = ref<Message[]>([])
const userInput = ref('')
const loading = ref(false)
const messagesContainer = ref<HTMLElement>()
const inputTextarea = ref<HTMLTextAreaElement>()
const abortController = ref<AbortController | null>(null)
const threadId = useStorage(localStorageKey.threadId, uuidv4())
const showCheckpoints = ref(false)
const saver = new IndexedDBSaver()
const currentCheckpointId = ref<string>('')
const useWordFormatting = ref(true)
const useSelectedText = ref(true)
const insertType = ref<insertTypes>('replaceAll')

const errorIssue = ref<boolean | string | null>(false)
const displayHistory = computed(() => {
  return history.value.filter(msg => {
    if (msg instanceof SystemMessage) return false
    if (msg instanceof AIMessage && !getMessageText(msg).trim()) return false
    return true
  })
})

onMounted(() => {
  document.addEventListener('click', (e) => {
    if (quickActionsRef.value && !quickActionsRef.value.contains(e.target)) {
      showQuickActions.value = false
    }
  })

  Office.context.document.addHandlerAsync(
    Office.EventType.DocumentSelectionChanged,
    fetchSelectedTextPreview
  )
})

const pendingFiles = ref<Array<{
  name: string
  type: string
  base64: string
  size: number
}>>([])
const uploadPending = computed(() => pendingFiles.value.length > 0)

async function handleAddFilesOrPhotos(): Promise<void> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.multiple = true
    input.accept = '*/*'

    input.onchange = async () => {
      const files = Array.from(input.files || [])
      if (files.length === 0) {
        resolve()
        return
      }

      try {
        for (const file of files) {
          const base64 = await new Promise<string | null>((res) => {
            const reader = new FileReader()
            reader.onload = () => {
              const result = reader.result as string
              const cleanBase64 = result.includes(',')
                ? result.split(',')[1]
                : result
              res(cleanBase64)
            }
            reader.onerror = () => res(null)
            reader.readAsDataURL(file)
          })

          if (!base64) continue
          pendingFiles.value.push({
            name: file.name,
            type: file.type || file.name.split('.').pop()?.toUpperCase() || 'FILE',
            base64,
            size: file.size,
          })
        }
      } catch (err) {
        console.error(err)
        messageUtil.error(`Upload failed. Please try again later.`)
      }
      resolve()
    }
    input.addEventListener('cancel', () => resolve())
    input.click()
  })
}

function removePendingFile(idx: number): void {
  pendingFiles.value.splice(idx, 1)
}

function getFileType(file: { name: string; type: string }): string {
  const ext = file.name.split('.').pop()?.toUpperCase()
  return ext || 'FILE'
}

function buildFilePayloads() {
  return pendingFiles.value.map((file) => ({
    filename: file.name,
    filepath: 'input',
    document_base64: file.base64,
  }))
}

function clearPendingFiles(): void {
  pendingFiles.value = []
}

async function fetchSelectedTextPreview() {
  try {
    const text = await Word.run(async ctx => {
      const range = ctx.document.getSelection()
      range.load('text')
      await ctx.sync()
      return range.text?.trim() || ''
    })
    if (!text) {
      selectedTextPreview.value = ''
      dismissedSelectedText.value = ''
    } else if (text !== dismissedSelectedText.value) {
      dismissedSelectedText.value = ''
      selectedTextPreview.value = text
    }
    // text === dismissedSelectedText: keep preview hidden
  } catch {
    selectedTextPreview.value = ''
  }
}

function dismissSelectedTextPreview() {
  dismissedSelectedText.value = selectedTextPreview.value
  selectedTextPreview.value = ''
}

function loadEnabledWordTools(): WordToolName[] {
  const stored = localStorage.getItem('enabledWordTools')
  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      return parsed.filter((name: string) => allWordToolNames.includes(name as WordToolName))
    } catch {
      return [...allWordToolNames]
    }
  }
  return [...allWordToolNames]
}

function loadEnabledGeneralTools(): GeneralToolName[] {
  const stored = localStorage.getItem('enabledGeneralTools')
  if (stored) {
    try {
      const parsed = JSON.parse(stored)
      return parsed.filter((name: string) => allGeneralToolNames.includes(name as GeneralToolName))
    } catch {
      return [...allGeneralToolNames]
    }
  }
  return [...allGeneralToolNames]
}

function getActiveTools() {
  const wordTools = createWordTools(enabledWordTools.value)
  const generalTools = createGeneralTools(enabledGeneralTools.value)
  return [...generalTools, ...wordTools]
}

function loadSavedPrompts() {
  const stored = localStorage.getItem('savedPrompts')
  if (stored) {
    try {
      savedPrompts.value = JSON.parse(stored)
    } catch (error) {
      console.error('Error loading saved prompts:', error)
      savedPrompts.value = []
    }
  }
}

function loadSelectedPrompt() {
  if (!selectedPromptId.value) {
    customSystemPrompt.value = ''
    return
  }

  const prompt = savedPrompts.value.find(p => p.id === selectedPromptId.value)
  if (prompt) {
    customSystemPrompt.value = prompt.systemPrompt
    userInput.value = prompt.userPrompt
    adjustTextareaHeight()

    if (inputTextarea.value) {
      inputTextarea.value.focus()
    }
  }
}

function handleUploadDocument() {
  const url = Office.context.document.url
  syncFileName.value = url ? url.split(/[\\/]/).pop() || 'Document' : 'Document'
  new_sync.value = true
}

async function handleGetDocument() {
  try {
    const result = await getCurrentDocument()
    await insertToDocument(result, 'replaceAll')
    messageUtil.success(`Document synced!`)
  } catch (err) {
    console.error(err)
    messageUtil.error('Failed to sync document')
  }
}

const quickActions: {
  key: keyof typeof buildInPrompt
  label: string
  icon: any
}[] = [
  { key: 'translate', label: t('translate'), icon: Globe },
  { key: 'polish', label: t('polish'), icon: Sparkle },
  { key: 'academic', label: t('academic'), icon: BookOpen },
  { key: 'summary', label: t('summary'), icon: FileCheck },
  { key: 'grammar', label: t('grammar'), icon: CheckCircle },
]

const getCustomModels = (key: string, oldKey: string): string[] => {
  const stored = localStorage.getItem(key)
  if (stored) {
    try {
      return JSON.parse(stored)
    } catch {
      return []
    }
  }
  const oldModel = localStorage.getItem(oldKey)
  if (oldModel && oldModel.trim()) {
    return [oldModel]
  }
  return []
}

const currentModelOptions = computed(() => {
  let presetOptions: string[] = []
  let customModels: string[] = []

  switch (settingForm.value.api) {
    case 'official':
      presetOptions = settingPreset.officialModelSelect.optionList || []
      customModels = getCustomModels('customModels', 'customModel')
      break
    case 'gemini':
      presetOptions = settingPreset.geminiModelSelect.optionList || []
      customModels = getCustomModels('geminiCustomModels', 'geminiCustomModel')
      break
    case 'ollama':
      presetOptions = settingPreset.ollamaModelSelect.optionList || []
      customModels = getCustomModels('ollamaCustomModels', 'ollamaCustomModel')
      break
    case 'groq':
      presetOptions = settingPreset.groqModelSelect.optionList || []
      customModels = getCustomModels('groqCustomModels', 'groqCustomModel')
      break
    case 'azure':
      return []
    default:
      return []
  }

  return [...presetOptions, ...customModels]
})

const currentModelSelect = computed({
  get() {
    switch (settingForm.value.api) {
      case 'official':
        return settingForm.value.officialModelSelect
      case 'gemini':
        return settingForm.value.geminiModelSelect
      case 'ollama':
        return settingForm.value.ollamaModelSelect
      case 'groq':
        return settingForm.value.groqModelSelect
      case 'azure':
        return settingForm.value.azureDeploymentName
      default:
        return ''
    }
  },
  set(value) {
    switch (settingForm.value.api) {
      case 'official':
        settingForm.value.officialModelSelect = value
        localStorage.setItem(localStorageKey.model, value)
        break
      case 'gemini':
        settingForm.value.geminiModelSelect = value
        localStorage.setItem(localStorageKey.geminiModel, value)
        break
      case 'ollama':
        settingForm.value.ollamaModelSelect = value
        localStorage.setItem(localStorageKey.ollamaModel, value)
        break
      case 'groq':
        settingForm.value.groqModelSelect = value
        localStorage.setItem(localStorageKey.groqModel, value)
        break
      case 'azure':
        settingForm.value.azureDeploymentName = value
        localStorage.setItem(localStorageKey.azureDeploymentName, value)
        break
    }
  },
})

function settings() {
  // FIXME: 使用路由方式会改变当前的threadID,进而重置页面
  router.push('/settings')
}

function file_system () {
  router.push('/filesystem')
}

function checkPoints() {
  showCheckpoints.value = true
}

function startNewChat() {
  if (loading.value) {
    stopGeneration()
  }
  userInput.value = ''
  history.value = []
  threadId.value = uuidv4()
  customSystemPrompt.value = ''
  selectedPromptId.value = ''
  pendingInterrupt.value = false  
  interruptMessage.value = ''    
  adjustTextareaHeight()
}

function stopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  loading.value = false
}

function adjustTextareaHeight() {
  if (inputTextarea.value) {
    inputTextarea.value.style.height = 'auto'
    inputTextarea.value.style.height = Math.min(inputTextarea.value.scrollHeight, 120) + 'px'
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

async function applyQuickAction(actionKey: keyof typeof buildInPrompt) {
  if (!checkApiKey()) return

  const selectedText = await Word.run(async ctx => {
    const range = ctx.document.getSelection()
    range.load('text')
    await ctx.sync()
    return range.text
  })

  if (!selectedText) {
    messageUtil.error(t('selectTextPrompt'))
    return
  }

  const builtInPrompts = getBuiltInPrompt()
  const action = builtInPrompts[actionKey]
  const settings = settingForm.value
  const { replyLanguage: lang } = settings

  const systemMessage = action.system(lang)
  const userMessage = new HumanMessage(action.user(selectedText, lang))

  scrollToBottom()

  loading.value = true
  abortController.value = new AbortController()

  try {
    await processChat(userMessage, systemMessage)
  } catch (error: any) {
    if (error.name === 'AbortError') {
      messageUtil.info(t('generationStop'))
    } else {
      console.error(error)
      messageUtil.error(t('failedToProcessAction'))
      // Remove failed message
      history.value.pop()
    }
  } finally {
    loading.value = false
    abortController.value = null
  }
}

function makeAgentCallbacks() {
  const seenToolCalls = new Set<string>()
  return {
    onStream: (text: string) => {
      const lastIndex = history.value.length - 1
      history.value[lastIndex] = new AIMessage(text)
      scrollToBottom()
    },
    onToolCall: (toolName: string, args: any, toolCallId?: string) => {
      console.log(toolName, args)
      if (toolCallId && seenToolCalls.has(toolCallId)) {
        return
      }
      if (toolCallId) seenToolCalls.add(toolCallId)
      if (toolName === 'write_file' && (args?.file_path === '/output/output.md' || arg?.filepath === 'output/output.md')) {
        messageUtil.success("Current file changed. Sync for updates.")
      }
      if (toolName === 'edit_file' && (args?.file_path === '/output/output.md' || arg?.filepath === 'output/output.md')) {
        messageUtil.success("Current file changed. Sync for updates.")
      }
      if (toolName === 'task' && args?.subagent_type === 'general-purpose') {
        console.log(args?.description)
      }

      const lastIndex = history.value.length - 1
      if (toolName === 'request_user_input') {
        const message = args?.message || 'Input required'
        pendingInterrupt.value = true
        interruptMessage.value = message
        history.value[lastIndex] = new AIMessage(`⏸️ ${message}`)
        scrollToBottom()
        return
      }
      const currentContent = getMessageText(history.value[lastIndex])
      history.value[lastIndex] = new AIMessage(currentContent + `\n\n🔧 Calling tool: ${toolName}...`)

      scrollToBottom()
    },
    onToolResult: (toolName: string, result: string) => {
      const lastIndex = history.value.length - 1
      const currentContent = getMessageText(history.value[lastIndex])

      history.value[lastIndex] = new AIMessage(
        currentContent.replace(
          `🔧 Calling tool: ${toolName}...`,
          `✅ Tool ${toolName} completed`
        )
      )

      scrollToBottom()
    },
    onInterrupt: (msg: string) => {
      pendingInterrupt.value = true
      interruptMessage.value = msg
      const lastIndex = history.value.length - 1
      history.value[lastIndex] = new AIMessage(`⏸️ ${msg}`)
      scrollToBottom()
    },
  }
}

async function sendMessage() {
  if ((!userInput.value.trim() && pendingFiles.value.length === 0 && !selectedTextPreview.value && !new_sync.value) || loading.value) return
  if (!checkApiKey()) return
  if (loading.value) return

  const userMessage = userInput.value.trim()
  const isResuming = ref(false)
  userInput.value = ''
  adjustTextareaHeight()

  if (pendingInterrupt.value && mode.value === 'agent') {
    if (isResuming.value) return

    isResuming.value = true
    await resumeAgent(userMessage)
    isResuming.value = false
    return
  }

  let messageContent = userMessage

  if (selectedTextPreview.value) {
    messageContent += `\n\n[Selected text]:\n${selectedTextPreview.value}`
    selectedTextPreview.value = ''
    dismissedSelectedText.value = ''
  }

  if (new_sync.value) {
    try {
      await uploadCurrentDocument()
      messageUtil.success('Document synced!')
    } catch (err) {
      console.error(err)
      messageUtil.error('Failed to sync document')
    }
    messageContent += `\n\n[Sync]: I have modified our shared file (output/output.md) with my current document. Check.`
  }

  loading.value = true
  abortController.value = new AbortController()

  try {
    let messageToSend: HumanMessage
    if (pendingFiles.value.length > 0) {
      const filePayloads = buildFilePayloads()
      await Promise.all(filePayloads.map(payload => uploadInputDocument(payload).catch(err => console.error('File upload failed:', err))))
      const fileNames = pendingFiles.value.map(f => f.name).join(', ')
      const fullText = messageContent
        ? `${messageContent}\n\n[Attached files]: ${fileNames}`
        : `[Attached files]: ${fileNames}`

      messageToSend = new HumanMessage({
        content: [
          ...filePayloads.map(payload => ({
            type: 'document' as const,
            source: {
              type: 'base64' as const,
              media_type: 'application/octet-stream',
              data: payload.document_base64,
            },
          })),
          {
            type: 'text' as const,
            text: fullText,
          },
        ],
      })
      clearPendingFiles()
    } else {
      messageToSend = new HumanMessage(messageContent)
    }

    if (new_sync.value) {
      new_sync.value = false
    }

    await processChat(messageToSend)

  } catch (error: any) {
    if (error.name === 'AbortError') {
      messageUtil.info(t('generationStop'))
    } else {
      console.error(error)
      messageUtil.error(t('failedToResponse'))
      history.value.pop()
    }
  } finally {
    loading.value = false
    abortController.value = null
  }
}

async function resumeAgent(userResumeInput: string) {
  interruptMessage.value = ''
  history.value.push(new HumanMessage(userResumeInput))
  history.value.push(new AIMessage(''))
  loading.value = true
  abortController.value = new AbortController()

  const settings = settingForm.value
  const { replyLanguage: lang, api: provider } = settings

  const providerConfigs: Record<string, any> = {
    official: {
      provider: 'official',
      config: {
        apiKey: settings.officialAPIKey,
        baseURL: settings.officialBasePath,
        dangerouslyAllowBrowser: true,
      },
      maxTokens: settings.officialMaxTokens,
      temperature: settings.officialTemperature,
      model: settings.officialModelSelect,
    },
    groq: {
      provider: 'groq',
      groqAPIKey: settings.groqAPIKey,
      groqModel: settings.groqModelSelect,
      maxTokens: settings.groqMaxTokens,
      temperature: settings.groqTemperature,
    },
    azure: {
      provider: 'azure',
      azureAPIKey: settings.azureAPIKey,
      azureAPIEndpoint: settings.azureAPIEndpoint,
      azureDeploymentName: settings.azureDeploymentName,
      azureAPIVersion: settings.azureAPIVersion,
      maxTokens: settings.azureMaxTokens,
      temperature: settings.azureTemperature,
    },
    gemini: {
      provider: 'gemini',
      geminiAPIKey: settings.geminiAPIKey,
      maxTokens: settings.geminiMaxTokens,
      temperature: settings.geminiTemperature,
      geminiModel: settings.geminiModelSelect,
    },
    ollama: {
      provider: 'ollama',
      ollamaEndpoint: settings.ollamaEndpoint,
      ollamaModel: settings.ollamaModelSelect,
      temperature: settings.ollamaTemperature,
    },
  }

  const currentConfig = providerConfigs[provider]
  if (!currentConfig) {
    messageUtil.error(t('notSupportedProvider'))
    return
  }

  try {
    await getAgentResponse({
      ...currentConfig,
      resumeValue: userResumeInput,
      messages: [],
      tools: getActiveTools(),
      recursionLimit: settings.agentMaxIterations,
      errorIssue,
      loading,
      abortSignal: abortController.value?.signal,
      threadId: threadId.value,
      ...makeAgentCallbacks(),  
    })
  } catch (error: any) {
    if (error.name === 'AbortError') {
      messageUtil.info(t('generationStop'))
    } else {
      messageUtil.error(t('failedToResponse'))
      history.value.pop()
    }
  } finally {
    pendingInterrupt.value = false
    loading.value = false
    abortController.value = null
  }
}

const agentPrompt = (lang: string) =>
  `
# Role
You are a highly skilled Microsoft Word Expert Agent. Your goal is to assist users in creating, editing, and formatting documents with professional precision.

# Capabilities
- You can interact with the document directly using provided tools (reading text, applying styles, inserting content, etc.).
- You understand document structure, typography, and professional writing standards.

# Guidelines
1. **Tool First**: If a request requires document modification or inspection or web search and fetch, prioritize using the available tools.
2. **Accuracy**: Ensure formatting and content changes are precise and follow the user's intent.
3. **Conciseness**: Provide brief, helpful explanations of your actions.
4. **Language**: You must communicate entirely in ${lang}.

# Safety
Do not perform destructive actions (like clearing the whole document) unless explicitly instructed.
`.trim()

const standardPrompt = (lang: string) =>
  `You are a helpful Microsoft Word specialist. Help users with drafting, brainstorming, and Word-related questions. Reply in ${lang}.`

async function processChat(userMessage: HumanMessage, systemMessage?: string) {
  const settings = settingForm.value
  const { replyLanguage: lang, api: provider } = settings
  const isAgentMode = mode.value === 'agent'

  const finalSystemMessage =
    customSystemPrompt.value || systemMessage || (isAgentMode ? agentPrompt(lang) : standardPrompt(lang))

  const defaultSystemMessage = new SystemMessage(finalSystemMessage)

  // Add user message to history
  history.value.push(userMessage)

  // Prepare messages for LLM (always include system message first, followed by all history)
  const finalMessages = [defaultSystemMessage, ...history.value]
  // Build provider configuration
  const providerConfigs: Record<string, any> = {
    official: {
      provider: 'official',
      config: {
        apiKey: settings.officialAPIKey,
        baseURL: settings.officialBasePath,
        dangerouslyAllowBrowser: true,
      },
      maxTokens: settings.officialMaxTokens,
      temperature: settings.officialTemperature,
      model: settings.officialModelSelect,
    },
    groq: {
      provider: 'groq',
      groqAPIKey: settings.groqAPIKey,
      groqModel: settings.groqModelSelect,
      maxTokens: settings.groqMaxTokens,
      temperature: settings.groqTemperature,
    },
    azure: {
      provider: 'azure',
      azureAPIKey: settings.azureAPIKey,
      azureAPIEndpoint: settings.azureAPIEndpoint,
      azureDeploymentName: settings.azureDeploymentName,
      azureAPIVersion: settings.azureAPIVersion,
      maxTokens: settings.azureMaxTokens,
      temperature: settings.azureTemperature,
    },
    gemini: {
      provider: 'gemini',
      geminiAPIKey: settings.geminiAPIKey,
      maxTokens: settings.geminiMaxTokens,
      temperature: settings.geminiTemperature,
      geminiModel: settings.geminiModelSelect,
    },
    ollama: {
      provider: 'ollama',
      ollamaEndpoint: settings.ollamaEndpoint,
      ollamaModel: settings.ollamaModelSelect,
      temperature: settings.ollamaTemperature,
    },
  }

  const currentConfig = providerConfigs[provider]
  if (!currentConfig) {
    messageUtil.error(t('notSupportedProvider'))
    return
  }

  history.value.push(new AIMessage(''))
  if (isAgentMode) {
    const tools = getActiveTools()

    await getAgentResponse({
      ...currentConfig,
      recursionLimit: settings.agentMaxIterations,
      messages: finalMessages,
      tools,
      errorIssue,
      loading,
      abortSignal: abortController.value?.signal,
      threadId: threadId.value,
      checkpointId: currentCheckpointId.value,
      ...makeAgentCallbacks(), 
    })
  }

  if (errorIssue.value) {
    if (typeof errorIssue.value === 'string') {
      messageUtil.error(t(errorIssue.value))
    } else {
      messageUtil.error(t('somethingWentWrong'))
    }
    errorIssue.value = null
    return
  }

  scrollToBottom()
}

async function insertToDocument(content: string, type: insertTypes) {
  insertType.value = type

  if (useWordFormatting.value) {
    await insertFormattedResult(content, insertType)
  } else {
    insertResult(content, insertType)
  }
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
  messageUtil.success(t('copied'))
}

function checkApiKey() {
  return true
}

const THINK_TAG = '<think>'
const THINK_TAG_END = '</think>'

interface RenderSegment {
  type: 'text' | 'think'
  text: string
}

// ── Markdown → HTML renderer ─────────────────────────────────────────────────

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderInline(text: string): string {
  // Ordered longest-match first: *** > ** > *, ___ > __ > _
  const pattern =
    /\*\*\*(.+?)\*\*\*|\*\*(.+?)\*\*|\*(.+?)\*|___(.+?)___|__(.+?)__|_(.+?)_|`([^`]+)`|\[([^\]]+)\]\([^)]+\)/g
  let result = ''
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) result += escapeHtml(text.slice(lastIndex, match.index))
    const [, bi1, b1, i1, bi2, b2, i2, code, link] = match
    if (bi1 !== undefined)       result += `<strong><em>${escapeHtml(bi1)}</em></strong>`
    else if (b1 !== undefined)   result += `<strong>${escapeHtml(b1)}</strong>`
    else if (i1 !== undefined)   result += `<em>${escapeHtml(i1)}</em>`
    else if (bi2 !== undefined)  result += `<strong><em>${escapeHtml(bi2)}</em></strong>`
    else if (b2 !== undefined)   result += `<strong>${escapeHtml(b2)}</strong>`
    else if (i2 !== undefined)   result += `<em>${escapeHtml(i2)}</em>`
    else if (code !== undefined) result += `<code>${escapeHtml(code)}</code>`
    else if (link !== undefined) result += `<span>${escapeHtml(link)}</span>`
    lastIndex = pattern.lastIndex
  }
  if (lastIndex < text.length) result += escapeHtml(text.slice(lastIndex))
  return result
}

function parseTableRow(line: string): string[] {
  return line.trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map(cell => cell.trim())
}

function markdownToHtml(markdown: string): string {
  const lines = markdown.trim().split('\n')
  const parts: string[] = []
  let i = 0
  let openList = ''

  const closeList = () => {
    if (openList) { parts.push(`</${openList}>`); openList = '' }
  }

  while (i < lines.length) {
    const line = lines[i]

    // Fenced code block
    if (line.trim().startsWith('```')) {
      closeList()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(escapeHtml(lines[i]))
        i++
      }
      i++
      parts.push(`<pre><code>${codeLines.join('\n')}</code></pre>`)
      continue
    }

    // Heading
    const hm = line.match(/^(#{1,6})\s+(.+?)(?:\s+#+)?$/)
    if (hm) {
      closeList()
      const tag = `h${hm[1].length}`
      parts.push(`<${tag}>${renderInline(hm[2])}</${tag}>`)
      i++; continue
    }

    // Blockquote
    if (line.trimStart().startsWith('>')) {
      closeList()
      parts.push(`<blockquote>${renderInline(line.replace(/^\s*>\s?/, ''))}</blockquote>`)
      i++; continue
    }

    // Bullet list
    const bm = line.match(/^(\s*)[-*+]\s+(.+)/)
    if (bm) {
      if (openList !== 'ul') { closeList(); parts.push('<ul>'); openList = 'ul' }
      parts.push(`<li>${renderInline(bm[2])}</li>`)
      i++; continue
    }

    // Numbered list
    const nm = line.match(/^(\s*)\d+\.\s+(.+)/)
    if (nm) {
      if (openList !== 'ol') { closeList(); parts.push('<ol>'); openList = 'ol' }
      parts.push(`<li>${renderInline(nm[2])}</li>`)
      i++; continue
    }

    // Table
    if (line.trim().startsWith('|')) {
      const nextLine = lines[i + 1]?.trim() || ''
      if (nextLine.match(/^\|[-:\s|]+\|/)) {
        closeList()
        const headers = parseTableRow(line)
        i += 2 // skip header row and separator row
        const rows: string[][] = []
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          rows.push(parseTableRow(lines[i]))
          i++
        }
        const headerHtml = headers.map(h => `<th>${renderInline(h)}</th>`).join('')
        const bodyHtml = rows.map(row =>
          `<tr>${row.map(cell => `<td>${renderInline(cell)}</td>`).join('')}</tr>`
        ).join('')
        parts.push(`<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>`)
        continue
      }
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(line.trim())) {
      closeList(); parts.push('<hr/>'); i++; continue
    }

    // Blank line
    if (!line.trim()) {
      closeList(); i++; continue
    }

    // Paragraph
    closeList()
    parts.push(`<p>${renderInline(line)}</p>`)
    i++
  }

  closeList()
  return parts.join('')
}

const flattenContentArray = (content: any[]): string =>
  content
    .map((part: any) => {
      if (typeof part === 'string') return part
      if (part?.text && typeof part.text === 'string') return part.text
      if (part?.data && typeof part.data === 'string') return part.data
      return ''
    })
    .join('')

const getMessageText = (msg: Message): string => {
  if (typeof msg.content === 'string') return msg.content

  if (Array.isArray(msg.content)) { 
    return msg.content.map((part: any) => {
      if (typeof part === 'string') return part
      if (part?.text) return part.text
      return ''
    }).join('')
  }

  if ((msg as any).lc_kwargs?.content) { return (msg as any).lc_kwargs.content }
  return ''
}

const cleanMessageText = (msg: Message): string => {
  const raw = getMessageText(msg)
  const regex = new RegExp(`${THINK_TAG}[\\s\\S]*?${THINK_TAG_END}`, 'g')
  return raw.replace(regex, '').trim()
}

const splitThinkSegments = (text: string): RenderSegment[] => {
  if (!text) return []

  const segments: RenderSegment[] = []
  let cursor = 0

  while (cursor < text.length) {
    const start = text.indexOf(THINK_TAG, cursor)
    if (start === -1) {
      segments.push({ type: 'text', text: text.slice(cursor) })
      break
    }

    if (start > cursor) {
      segments.push({ type: 'text', text: text.slice(cursor, start) })
    }

    const end = text.indexOf(THINK_TAG_END, start + THINK_TAG.length)
    if (end === -1) {
      segments.push({
        type: 'think',
        text: text.slice(start + THINK_TAG.length),
      })
      break
    }

    segments.push({
      type: 'think',
      text: text.slice(start + THINK_TAG.length, end),
    })
    cursor = end + THINK_TAG_END.length
  }

  return segments.filter(segment => segment.text)
}

const renderSegments = (msg: Message): RenderSegment[] => {
  const raw = getMessageText(msg)
  return splitThinkSegments(raw)
}

const addWatch = () => {
  watch(
    () => settingForm.value.replyLanguage,
    () => {
      localStorage.setItem(localStorageKey.replyLanguage, settingForm.value.replyLanguage)
    },
  )
  watch(
    () => settingForm.value.api,
    () => {
      localStorage.setItem(localStorageKey.api, settingForm.value.api)
    },
  )
}

async function initData() {
  insertType.value = (localStorage.getItem(localStorageKey.insertType) as insertTypes) || 'replace'
}

async function handleRestore(checkpointId: string) {
  currentCheckpointId.value = checkpointId
  showCheckpoints.value = false

  // Fetch the history up to the selected checkpoint
  const checkpointTuple = await saver.getTuple({
    configurable: { thread_id: threadId.value, checkpoint_id: checkpointId },
  })

  if (checkpointTuple) {
    const messages = checkpointTuple.checkpoint.channel_values.messages
    if (messages && Array.isArray(messages)) {
      history.value = messages
        .filter((msg: any) => ['human', 'ai'].includes(msg.type))
        .map((msg: any) => {
          return msg.type === 'human'
            ? new HumanMessage({ content: msg.content ?? '' })
            : new AIMessage({ content: msg.content ?? '' })
        })
    }
  }
}

async function loadThreadHistory(targetThreadId: string) {
  const checkpoints: CheckpointTuple[] = []
  const iterator = saver.list({
    configurable: { thread_id: targetThreadId },
  })

  for await (const checkpoint of iterator) {
    checkpoints.push(checkpoint)
  }

  if (checkpoints.length > 0) {
    checkpoints.sort((a, b) => (a.metadata?.step ?? 0) - (b.metadata?.step ?? 0))

    const latestCheckpoint = checkpoints[checkpoints.length - 1]
    const messages = latestCheckpoint.checkpoint.channel_values.messages
    // TODO: 优化过滤策略
    if (messages && Array.isArray(messages)) {
      history.value = messages
        .filter((msg: any) => ['human', 'ai'].includes(msg.type))
        .map((msg: any) => {
          return msg.type === 'human'
            ? new HumanMessage({ content: msg.content ?? '' })
            : new AIMessage({ content: msg.content ?? '' })
        })
      currentCheckpointId.value = latestCheckpoint.config.configurable?.checkpoint_id || ''
    } else {
      history.value = []
      currentCheckpointId.value = ''
    }
  } else {
    // No checkpoints found for this thread
    history.value = []
    currentCheckpointId.value = ''
  }
  await scrollToBottom()
}

async function handleSelectThread(newThreadId: string) {
  threadId.value = newThreadId
  showCheckpoints.value = false
  await loadThreadHistory(newThreadId)
}

onBeforeMount(() => {
  addWatch()
  initData()
  loadSavedPrompts()

  if (threadId.value) {
    loading.value = true // 可选：显示加载状态
    try {
      loadThreadHistory(threadId.value)
    } catch (e) {
      console.error('Auto reload history failed:', e)
    } finally {
      loading.value = false
    }
  }
})
</script>

<style scoped>
/* Markdown rendered inside AI message bubbles */
.ai-markdown :deep(p)          { margin: 0.15em 0; }
.ai-markdown :deep(h1),
.ai-markdown :deep(h2)         { font-size: 1em; font-weight: 700; margin: 0.4em 0 0.15em; }
.ai-markdown :deep(h3),
.ai-markdown :deep(h4),
.ai-markdown :deep(h5),
.ai-markdown :deep(h6)         { font-weight: 600; margin: 0.3em 0 0.1em; }
.ai-markdown :deep(strong)     { font-weight: 700; }
.ai-markdown :deep(em)         { font-style: italic; }
.ai-markdown :deep(code)       { font-family: 'Consolas', monospace; font-size: 0.9em;
                                  background: rgba(255,255,255,0.06); border-radius: 3px;
                                  padding: 0 3px; }
.ai-markdown :deep(pre)        { background: #0d0f12; border-radius: 4px; padding: 6px 8px;
                                  margin: 0.3em 0; overflow-x: auto; }
.ai-markdown :deep(pre code)   { background: none; padding: 0; font-size: 0.88em; }
.ai-markdown :deep(ul)         { list-style: disc; padding-left: 1.2em; margin: 0.2em 0; }
.ai-markdown :deep(ol)         { list-style: decimal; padding-left: 1.2em; margin: 0.2em 0; }
.ai-markdown :deep(li)         { margin: 0.1em 0; }
.ai-markdown :deep(blockquote) { border-left: 2px solid rgba(0,164,138,0.4);
                                  padding-left: 0.5em; color: rgba(255,255,255,0.6);
                                  font-style: italic; margin: 0.2em 0; }
.ai-markdown :deep(hr)         { border-color: rgba(255,255,255,0.1); margin: 0.4em 0; }
.ai-markdown :deep(table)      { border-collapse: collapse; width: 100%; margin: 0.3em 0; font-size: 0.9em; }
.ai-markdown :deep(th),
.ai-markdown :deep(td)         { border: 1px solid rgba(255,255,255,0.12); padding: 3px 8px; text-align: left; }
.ai-markdown :deep(thead tr)   { background: rgba(255,255,255,0.06); }
.ai-markdown :deep(tbody tr:nth-child(even)) { background: rgba(255,255,255,0.03); }
</style>
