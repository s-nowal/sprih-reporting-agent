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
          @click="rerouteHome"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <span class="flex-1 text-[10px] uppercase tracking-wider font-semibold text-[#ffffff]/70">Files</span>
        <button
          class="flex h-6 w-6 items-center justify-center rounded transition-colors"
          :class="rootDir ? 'text-[#00a48a]' : 'text-[#ffffff]/70 hover:bg-[#ffffff]/5 hover:text-[#ffffff]/80'"
          :title="rootDir ? `Root: ${rootDir.name}` : 'Set download folder'"
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
      <div class="flex flex-1 flex-col overflow-hidden rounded-sm border border-[#ffffff]/5 bg-[#0a0c0f]">
        <!-- Loading -->
        <div v-if="loading" class="flex h-full flex-col items-center justify-center gap-2">
          <div class="h-8 w-8 animate-spin rounded-full border-2 border-[#ffffff]/10 border-t-[#00a48a]"></div>
          <span class="text-[10px] text-[#ffffff]/50">Loading files…</span>
        </div>

        <!-- Error -->
        <div v-else-if="error" class="flex h-full flex-col items-center justify-center gap-2 text-red-400">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          <span class="text-[11px]">{{ error }}</span>
        </div>

        <!-- Empty -->
        <div v-else-if="documents.length === 0" class="flex h-full flex-col items-center justify-center gap-3">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#00a48a" stroke-width="1.5" opacity="0.4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          <span class="text-[11px] text-[#ffffff]/50">No files found</span>
        </div>

        <!-- Folder groups -->
        <div v-else class="flex flex-col gap-2 overflow-y-auto p-2">
          <div
            v-for="(group, folder) in groupedDocuments"
            :key="folder"
          >
            <!-- Folder header -->
            <button
              class="flex w-full items-center gap-1.5 rounded-sm px-1.5 py-1 text-left hover:bg-[#ffffff]/5 transition-colors"
              @click="toggleFolder(folder)"
            >
              <svg
                class="shrink-0 transition-transform duration-150 text-[#ffffff]/50"
                :class="{ 'rotate-0': openFolders[folder], '-rotate-90': !openFolders[folder] }"
                width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
              <svg class="shrink-0 text-[#00a48a]/80" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
              <span class="text-[11px] font-medium text-[#ffffff]/80">{{ folder }}</span>
              <span v-if="subDirHandle(folder)" class="ml-auto text-[9px] text-[#00a48a]/60 uppercase tracking-wider">linked</span>
            </button>

            <!-- File list -->
            <ul
              v-show="openFolders[folder]"
              class="mt-1 flex flex-col gap-1 pl-4 list-none m-0"
            >
              <li
                v-for="doc in group"
                :key="fileKey(doc)"
                class="group flex items-center gap-2 rounded-sm border border-[#ffffff]/6 bg-[#13161b] px-2 py-1.5 hover:border-[#00a48a]/40 transition-colors"
              >
                <svg class="shrink-0 text-[#00a48a]/70" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>

                <!-- Inline rename input -->
                <template v-if="renamingKey === fileKey(doc)">
                  <input
                    ref="renameInput"
                    v-model="renameValue"
                    class="flex-1 min-w-0 rounded bg-[#0d0f12] border border-[#00a48a]/40 px-1.5 py-0.5 text-[11px] text-[#ffffff] focus:outline-none"
                    @keydown.enter.prevent="confirmRename(doc)"
                    @keydown.escape.prevent="cancelRename"
                  />
                  <button
                    class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#00a48a] hover:bg-[#00a48a]/20 transition-colors"
                    title="Confirm rename"
                    @click="confirmRename(doc)"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                  </button>
                  <button
                    class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#ffffff]/50 hover:bg-[#ffffff]/10 transition-colors"
                    title="Cancel"
                    @click="cancelRename"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                  </button>
                </template>

                <!-- Normal file row -->
                <template v-else>
                  <div class="flex min-w-0 flex-1 flex-col">
                    <span class="truncate text-[11px] font-medium text-[#ffffff]/90" :title="doc.filename">{{ doc.filename }}</span>
                    <span class="text-[9px] uppercase tracking-widest text-[#ffffff]/40">{{ getExt(doc.filename) }}</span>
                  </div>

                  <!-- Rename button -->
                  <button
                    class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#ffffff]/40 opacity-0 group-hover:opacity-100 hover:bg-[#ffffff]/10 hover:text-[#ffffff]/80 transition-all"
                    title="Rename"
                    @click="startRename(doc)"
                  >
                    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                  </button>

                  <!-- Download button -->
                  <button
                    class="flex h-5 w-5 shrink-0 items-center justify-center rounded text-[#ffffff]/60 hover:bg-[#00a48a]/20 hover:text-[#00a48a] transition-colors disabled:opacity-30"
                    :disabled="downloading === fileKey(doc)"
                    :title="`Download ${doc.filename}`"
                    @click="handleDownload(doc)"
                  >
                    <svg v-if="downloading !== fileKey(doc)" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                      <polyline points="7 10 12 15 17 10"/>
                      <line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                    <div v-else class="h-3 w-3 animate-spin rounded-full border border-[#ffffff]/20 border-t-[#00a48a]"></div>
                  </button>
                </template>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { getAllDocuments, downloadDocument } from '@/api/docreader'

const router = useRouter()
const documents = ref([])
const loading = ref(true)
const error = ref(null)
const downloading = ref(null)
const openFolders = ref({})

// Directory handles
const rootDir = ref(null)
const subDirs = ref({})          // filepath → FileSystemDirectoryHandle
const localHandles = ref({})     // fileKey → { dirHandle, filename } for rename

// Rename state
const renamingKey = ref(null)
const renameValue = ref('')
const renameInput = ref(null)
const renameError = ref(null)

onMounted(async () => {
  try {
    documents.value = await getAllDocuments()
    for (const doc of documents.value) {
      const folder = doc.filepath ?? 'root'
      if (openFolders.value[folder] === undefined) openFolders.value[folder] = true
    }
  } catch (e) {
    error.value = 'Failed to load files.'
  } finally {
    loading.value = false
  }
})

const groupedDocuments = computed(() => {
  const groups = {}
  for (const doc of documents.value) {
    const folder = doc.filepath ?? 'root'
    if (!groups[folder]) groups[folder] = []
    groups[folder].push(doc)
  }
  return groups
})

function fileKey(doc) {
  return `${doc.filepath ?? 'root'}/${doc.filename}`
}

function subDirHandle(folder) {
  return subDirs.value[folder] ?? null
}

function toggleFolder(folder) {
  openFolders.value[folder] = !openFolders.value[folder]
}

function getExt(filename) {
  const parts = filename?.split('.')
  return parts?.length > 1 ? parts.at(-1).toUpperCase() : 'FILE'
}

function rerouteHome() {
  router.push('/')
}

async function getOrCreateSubdir(parent, name) {
  return parent.getDirectoryHandle(name, { create: true })
}

async function pickDownloadFolder() {
  if (!('showDirectoryPicker' in window)) return
  try {
    const dir = await window.showDirectoryPicker({ mode: 'readwrite' })
    rootDir.value = dir
    subDirs.value = {}
    const folders = new Set(
      documents.value.map(doc => doc.filepath).filter(fp => fp && fp !== 'root')
    )
    for (const folder of folders) {
      subDirs.value[folder] = await getOrCreateSubdir(dir, folder)
    }
  } catch (e) {
    if (e.name !== 'AbortError') console.error(e)
  }
}

async function handleDownload(doc) {
  const key = fileKey(doc)
  downloading.value = key
  try {
    let dirHandle = null
    if (rootDir.value) {
      const folder = doc.filepath
      if (folder && folder !== 'root') {
        if (!subDirs.value[folder]) {
          subDirs.value[folder] = await getOrCreateSubdir(rootDir.value, folder)
        }
        dirHandle = subDirs.value[folder]
      } else {
        dirHandle = rootDir.value
      }
    }
    await downloadDocument(doc, dirHandle)
    if (dirHandle) {
      localHandles.value[key] = { dirHandle, filename: doc.filename }
    }
  } finally {
    downloading.value = null
  }
}

// ── Rename ────────────────────────────────────────────────────────────────

async function startRename(doc) {
  renamingKey.value = fileKey(doc)
  renameValue.value = doc.filename
  renameError.value = null
  await nextTick()
  renameInput.value?.[0]?.focus()
  renameInput.value?.[0]?.select()
}

function cancelRename() {
  renamingKey.value = null
  renameValue.value = ''
  renameError.value = null
}

async function confirmRename(doc) {
  const newName = renameValue.value.trim()
  if (!newName || newName === doc.filename) {
    cancelRename()
    return
  }

  const oldKey = fileKey(doc)
  const handle = localHandles.value[oldKey]

  // Rename local file if it was previously downloaded
  if (handle) {
    try {
      const oldFileHandle = await handle.dirHandle.getFileHandle(doc.filename)
      const file = await oldFileHandle.getFile()
      const buffer = await file.arrayBuffer()

      const newFileHandle = await handle.dirHandle.getFileHandle(newName, { create: true })
      const writable = await newFileHandle.createWritable()
      await writable.write(buffer)
      await writable.close()

      await handle.dirHandle.removeEntry(doc.filename)

      // Re-track under new name
      const newKey = `${doc.filepath ?? 'root'}/${newName}`
      localHandles.value[newKey] = { dirHandle: handle.dirHandle, filename: newName }
      delete localHandles.value[oldKey]
    } catch (err) {
      console.error('Local rename failed:', err)
    }
  }

  // Update documents list
  const entry = documents.value.find(d => d.filepath === doc.filepath && d.filename === doc.filename)
  if (entry) entry.filename = newName

  cancelRename()
}
</script>
