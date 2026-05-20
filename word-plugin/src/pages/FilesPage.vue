<template>
  <div
    class="relative flex h-full w-full flex-col bg-bg p-2 text-main"
    style="font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; font-size: 13px;"
  >
    <div class="relative flex h-full w-full flex-col gap-1 rounded-md">
      <!-- Header -->
      <div class="flex items-center gap-1 rounded-sm border border-border bg-bg-secondary px-1.5 py-1">
        <button
          class="flex h-6 w-6 items-center justify-center rounded text-secondary hover:bg-hover hover:text-main transition-colors"
          @click="rerouteHome"
        >
          <ArrowLeft :size="13" />
        </button>
        <span class="flex-1 text-[10px] uppercase tracking-wider font-semibold text-secondary">Files</span>
        <button
          class="flex h-6 w-6 items-center justify-center rounded transition-colors"
          :class="rootDir ? 'text-accent' : 'text-secondary hover:bg-hover hover:text-main'"
          :title="rootDir ? `Save folder: ${rootDir.name}` : 'Set save folder'"
          @click="pickDownloadFolder"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            <line x1="12" y1="11" x2="12" y2="17"/>
            <polyline points="9 14 12 17 15 14"/>
          </svg>
        </button>
      </div>

      <!-- Content -->
      <div class="flex flex-1 flex-col overflow-hidden rounded-sm border border-border bg-bg-tertiary">
        <!-- No active thread -->
        <div v-if="!threadId" class="flex h-full flex-col items-center justify-center gap-2">
          <FileText :size="28" class="text-accent opacity-40" />
          <span class="text-[11px] text-tertiary">No active thread</span>
          <span class="text-[10px] text-tertiary">Start a conversation first</span>
        </div>

        <!-- Loading -->
        <div v-else-if="loading" class="flex h-full flex-col items-center justify-center gap-2">
          <div class="h-8 w-8 animate-spin rounded-full border-2 border-border border-t-accent"></div>
          <span class="text-[10px] text-tertiary">Loading files…</span>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex h-full flex-col items-center justify-center gap-2 text-danger">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span class="text-[11px]">{{ error }}</span>
        </div>

        <!-- Empty -->
        <div v-else-if="files.length === 0" class="flex h-full flex-col items-center justify-center gap-3">
          <FileText :size="28" class="text-accent opacity-40" />
          <span class="text-[11px] text-tertiary">No files in this thread</span>
        </div>

        <!-- Folder groups -->
        <div v-else class="flex flex-col gap-2 overflow-y-auto p-2">
          <div
            v-for="(group, folder) in groupedFiles"
            :key="folder"
          >
            <!-- Folder header -->
            <button
              class="flex w-full items-center gap-1.5 rounded-sm px-1.5 py-1 text-left hover:bg-hover transition-colors"
              @click="toggleFolder(String(folder))"
            >
              <svg
                class="shrink-0 transition-transform duration-150 text-secondary"
                :class="{ 'rotate-0': openFolders[String(folder)], '-rotate-90': !openFolders[String(folder)] }"
                width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
              <svg class="shrink-0 text-accent/80" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span class="text-[11px] font-medium text-main">{{ folder }}</span>
            </button>

            <!-- File list -->
            <ul
              v-show="openFolders[String(folder)]"
              class="mt-1 flex flex-col gap-1 pl-4 list-none m-0"
            >
              <li
                v-for="f in group"
                :key="f.key"
                class="group flex items-center gap-2 rounded-sm border border-border bg-bg-secondary px-2 py-1.5 hover:border-accent/40 transition-colors"
              >
                <FileText :size="13" class="shrink-0 text-accent/70" />
                <div class="flex min-w-0 flex-1 flex-col">
                  <span class="truncate text-[11px] font-medium text-main" :title="getFilename(f.key)">
                    {{ getFilename(f.key) }}
                  </span>
                  <span class="text-[9px] uppercase tracking-widest text-tertiary">
                    {{ getExt(getFilename(f.key)) }}
                  </span>
                </div>

                <!-- Download button -->
                <button
                  class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-secondary hover:bg-accent/15 hover:text-accent transition-colors disabled:opacity-30"
                  :disabled="downloading === f.key"
                  :title="`Download ${getFilename(f.key)}`"
                  @click="handleDownload(f)"
                >
                  <div v-if="downloading === f.key" class="h-3 w-3 animate-spin rounded-full border border-border border-t-accent"></div>
                  <Download v-else :size="11" />
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ArrowLeft, Download, FileText } from 'lucide-vue-next'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listFiles, readFile, type FileObject } from '@/api/files'

const THREAD_KEY = 'sprih.threadId'

const router = useRouter()
const threadId = ref<string | null>(localStorage.getItem(THREAD_KEY))
const files = ref<FileObject[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const downloading = ref<string | null>(null)
const openFolders = ref<Record<string, boolean>>({})
const rootDir = ref<FileSystemDirectoryHandle | null>(null)
const subDirs = ref<Record<string, FileSystemDirectoryHandle>>({})

onMounted(async () => {
  if (!threadId.value) return
  loading.value = true
  try {
    files.value = await listFiles(threadId.value)
    for (const f of files.value) {
      const folder = getFolder(f.key)
      if (openFolders.value[folder] === undefined) openFolders.value[folder] = true
    }
  } catch (e) {
    error.value = 'Failed to load files.'
  } finally {
    loading.value = false
  }
})

function getFolder(key: string): string {
  const parts = key.split('/')
  return parts.length > 1 ? parts.slice(0, -1).join('/') : 'root'
}

function getFilename(key: string): string {
  return key.split('/').pop() ?? key
}

function getExt(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.at(-1)!.toUpperCase() : 'FILE'
}

const groupedFiles = computed(() => {
  const groups: Record<string, FileObject[]> = {}
  for (const f of files.value) {
    const folder = getFolder(f.key)
    if (!groups[folder]) groups[folder] = []
    groups[folder].push(f)
  }
  return groups
})

function toggleFolder(folder: string) {
  openFolders.value[folder] = !openFolders.value[folder]
}

function rerouteHome() {
  router.push('/')
}

async function getOrCreateSubdir(
  parent: FileSystemDirectoryHandle,
  name: string,
): Promise<FileSystemDirectoryHandle> {
  return parent.getDirectoryHandle(name, { create: true })
}

async function pickDownloadFolder() {
  if (!('showDirectoryPicker' in window)) return
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const dir = await (window as any).showDirectoryPicker({ mode: 'readwrite' })
    rootDir.value = dir
    subDirs.value = {}
    const folders = new Set(
      files.value.map((f) => getFolder(f.key)).filter((fp) => fp !== 'root'),
    )
    for (const folder of folders) {
      subDirs.value[folder] = await getOrCreateSubdir(dir, folder)
    }
  } catch (e: unknown) {
    if ((e as { name?: string })?.name !== 'AbortError') console.error(e)
  }
}

async function handleDownload(f: FileObject) {
  if (!threadId.value) return
  downloading.value = f.key
  try {
    const result = await readFile(threadId.value, f.key)
    const filename = getFilename(f.key)
    const blob = result.is_binary
      ? new Blob([Uint8Array.from(atob(result.content), (c) => c.charCodeAt(0))])
      : new Blob([result.content], { type: 'text/plain' })

    const folder = getFolder(f.key)
    let dirHandle: FileSystemDirectoryHandle | null = null
    if (rootDir.value) {
      if (folder !== 'root') {
        if (!subDirs.value[folder]) {
          subDirs.value[folder] = await getOrCreateSubdir(rootDir.value, folder)
        }
        dirHandle = subDirs.value[folder]
      } else {
        dirHandle = rootDir.value
      }
    }

    if (dirHandle) {
      const fh = await dirHandle.getFileHandle(filename, { create: true })
      const writable = await fh.createWritable()
      await writable.write(blob)
      await writable.close()
      return
    }

    if ('showSaveFilePicker' in window) {
      try {
        const ext = filename.split('.').pop()
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const fh = await (window as any).showSaveFilePicker({
          suggestedName: filename,
          types: ext
            ? [{ description: 'File', accept: { '*/*': [`.${ext}`] } }]
            : undefined,
        })
        const writable = await fh.createWritable()
        await writable.write(blob)
        await writable.close()
        return
      } catch (e: unknown) {
        if ((e as { name?: string })?.name === 'AbortError') return
      }
    }

    // Fallback: anchor download
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Download failed:', e)
  } finally {
    downloading.value = null
  }
}
</script>
