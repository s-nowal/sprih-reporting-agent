<template>
  <div
    class="relative flex h-full w-full flex-col bg-bg p-2 text-main"
    style="font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; font-size: 14px"
  >
    <!-- Google Drive auth fallback (when popup/redirect is blocked) -->
    <div
      v-if="driveAuthUrl"
      class="absolute inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div class="mx-4 flex flex-col gap-3 rounded-md border border-border bg-bg p-4 shadow-lg">
        <span class="text-[13px] font-semibold text-main">Open this link to connect Google Drive</span>
        <a
          :href="driveAuthUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="break-all text-[11px] text-accent underline"
          @click="driveAuthUrl = null"
        >
          {{ driveAuthUrl }}
        </a>
        <p v-if="driveConnectError" class="text-[11px] text-danger">{{ driveConnectError }}</p>
        <button
          class="self-end rounded border border-border px-3 py-1.5 text-[11px] font-semibold text-secondary transition-colors hover:bg-hover hover:text-main"
          @click="driveAuthUrl = null; driveConnectError = null"
        >
          Dismiss
        </button>
      </div>
    </div>

    <!-- Google Drive connection prompt -->
    <div
      v-if="showDrivePrompt"
      class="absolute inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div class="mx-4 flex flex-col gap-4 rounded-md border border-border bg-bg p-4 shadow-lg">
        <div class="flex flex-col gap-1">
          <span class="text-[13px] font-semibold text-main">Connect Google Drive</span>
          <span class="text-[11px] leading-relaxed text-tertiary">
            Do you want to connect your Google Drive?
          </span>
        </div>
        <div class="flex justify-end gap-2">
          <button
            class="rounded border border-border px-3 py-1.5 text-[11px] font-semibold text-secondary transition-colors hover:bg-hover hover:text-main"
            @click="dismissDrivePrompt"
          >
            No
          </button>
          <button
            class="rounded bg-accent px-3 py-1.5 text-[11px] font-semibold text-on-accent transition-colors hover:bg-accent-hover"
            @click="onDrivePromptYes"
          >
            Yes
          </button>
        </div>
      </div>
    </div>
    <!-- Parent Folder ID prompt (shown after Drive auth redirect) -->
    <div
      v-if="showFolderIdPrompt"
      class="absolute inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div class="mx-4 flex flex-col gap-3 rounded-md border border-border bg-bg p-4 shadow-lg">
        <div class="flex items-center justify-between">
          <span class="text-[13px] font-semibold text-main">Google Drive Folder</span>
          <button
            class="flex h-5 w-5 items-center justify-center rounded text-secondary transition-colors hover:bg-hover hover:text-main"
            @click="showFolderIdPrompt = false"
          >
            <X :size="12" />
          </button>
        </div>
        <span class="text-[11px] leading-relaxed text-tertiary">
          Enter the ID of the parent Google Drive folder where thread folders will be created.
        </span>
        <input
          v-model="folderIdInput"
          type="text"
          placeholder="e.g. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs"
          class="rounded border border-border bg-bg-tertiary px-2 py-1.5 text-[12px] text-main placeholder-tertiary focus:border-accent/40 focus:outline-none"
          @keydown.enter.prevent="onFolderIdOk"
        />
        <div class="flex justify-end">
          <button
            class="rounded bg-accent px-3 py-1.5 text-[11px] font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
            :disabled="!folderIdInput.trim()"
            @click="onFolderIdOk"
          >
            OK
          </button>
        </div>
      </div>
    </div>

    <!-- Parent folder set successfully -->
    <div
      v-if="folderIdSuccess"
      class="absolute inset-0 z-50 flex items-center justify-center bg-black/40"
    >
      <div class="mx-4 flex flex-col gap-3 rounded-md border border-border bg-bg p-4 shadow-lg">
        <span class="text-[13px] font-semibold text-main">Drive folder connected ✓</span>
        <p class="text-[11px] leading-relaxed text-tertiary">
          The parent folder has been saved. Thread folders will be created inside it.
        </p>
        <button
          class="self-end rounded bg-accent px-3 py-1.5 text-[11px] font-semibold text-on-accent transition-colors hover:bg-accent-hover"
          @click="folderIdSuccess = false"
        >
          Done
        </button>
      </div>
    </div>

    <div class="relative flex h-full w-full flex-col gap-1 rounded-md">
      <!-- Header -->
      <div
        class="flex items-center gap-2 rounded-sm border border-border bg-bg-secondary px-2 py-1.5"
      >
        <img :src="sprihLogo" alt="Sprih" class="h-4 w-auto shrink-0" />
        <div class="flex min-w-0 flex-1 flex-col leading-tight">
          <span class="truncate text-[10px] text-tertiary">
            {{ headerSubtitle }}
          </span>
        </div>
        <div class="flex items-center gap-0.5">
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-secondary transition-colors hover:bg-hover hover:text-main disabled:opacity-40"
            title="New chat"
            :disabled="streaming"
            @click="newChat"
          >
            <Plus :size="13" />
          </button>
          <button
            class="flex h-6 w-6 items-center justify-center rounded transition-colors disabled:opacity-40"
            :class="
              viewMode === 'history'
                ? 'bg-accent/15 text-accent'
                : 'text-secondary hover:bg-hover hover:text-main'
            "
            :title="viewMode === 'history' ? 'Back to chat' : 'History'"
            :disabled="streaming"
            @click="toggleView('history')"
          >
            <History :size="13" />
          </button>
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-secondary transition-colors hover:bg-hover hover:text-main"
            :title="darkMode ? 'Switch to light mode' : 'Switch to dark mode'"
            @click="toggleDarkMode"
          >
            <Sun v-if="darkMode" :size="13" />
            <Moon v-else :size="13" />
          </button>
        </div>
      </div>

      <!-- History inline panel -->
      <div
        v-if="viewMode === 'history'"
        class="flex flex-1 flex-col gap-2 overflow-hidden rounded-sm border border-border bg-bg-tertiary p-2"
      >
        <span
          class="px-1 text-[10px] font-semibold uppercase tracking-widest text-tertiary"
        >
          Recent threads
        </span>
        <div v-if="historyLoading" class="text-[11px] italic text-tertiary px-1">
          Loading…
        </div>
        <div
          v-else-if="historyError"
          class="text-[11px] text-danger px-1"
        >
          {{ historyError }}
        </div>
        <div
          v-else-if="!historyThreads.length"
          class="flex h-full flex-col items-center justify-center gap-1 text-center"
        >
          <span class="text-[11px] text-tertiary">No threads yet</span>
          <span class="text-[10px] text-tertiary"
            >Create one with the + button above</span
          >
        </div>
        <ul v-else class="m-0 flex flex-col gap-1 overflow-y-auto p-0 list-none">
          <li v-for="t in historyThreads" :key="t.thread_id">
            <div
              class="group flex w-full items-center gap-1 rounded border px-2 py-1.5 transition-colors"
              :class="
                t.thread_id === threadId
                  ? 'border-accent/40 bg-accent/5'
                  : 'border-border bg-bg-secondary hover:bg-hover'
              "
            >
              <button
                class="flex min-w-0 flex-1 flex-col items-start gap-0.5 text-left"
                @click="loadThread(t)"
              >
                <span
                  class="truncate text-[12px] font-medium text-main w-full"
                  :title="t.title ?? `thread ${t.thread_id.slice(0, 8)}…`"
                >
                  {{ t.title ?? `thread ${t.thread_id.slice(0, 8)}…` }}
                </span>
                <span
                  class="text-[10px] uppercase tracking-wider text-tertiary"
                >
                  {{ formatRelativeTime(t.updated_at) }}
                </span>
              </button>
              <button
                class="flex h-6 w-6 shrink-0 items-center justify-center rounded text-tertiary opacity-60 transition-colors hover:bg-hover hover:text-main hover:opacity-100"
                title="Edit thread"
                @click.stop="openEditThread(t)"
              >
                <Pencil :size="11" />
              </button>
            </div>
          </li>
        </ul>
      </div>

      <!-- Edit thread panel -->
      <div
        v-else-if="viewMode === 'editThread' && editingThread"
        class="flex flex-1 flex-col gap-3 overflow-y-auto rounded-sm border border-border bg-bg-tertiary p-3"
      >
        <div class="flex items-center gap-2">
          <button
            class="flex h-6 w-6 items-center justify-center rounded text-secondary transition-colors hover:bg-hover hover:text-main"
            title="Back to history"
            @click="closeEditThread"
          >
            <ArrowLeft :size="13" />
          </button>
          <span
            class="text-[10px] font-semibold uppercase tracking-widest text-tertiary"
          >
            Edit thread
          </span>
        </div>

        <!-- Title section -->
        <section class="flex flex-col gap-1">
          <span class="text-[10px] font-semibold uppercase tracking-wider text-tertiary">
            Title
          </span>
          <div class="flex items-center gap-1">
            <input
              v-model="editTitle"
              type="text"
              :placeholder="`thread ${editingThread.thread_id.slice(0, 8)}…`"
              class="flex-1 rounded border border-border bg-bg px-2 py-1.5 text-[12px] text-main placeholder-tertiary focus:border-accent/40 focus:outline-none"
              @keydown.enter.prevent="saveTitle"
            />
            <button
              class="rounded bg-accent px-3 py-1.5 text-[11px] font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
              :disabled="!editTitle.trim() || savingTitle || editTitle === (editingThread.title ?? '')"
              @click="saveTitle"
            >
              {{ savingTitle ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </section>

        <!-- Drive folder section -->
        <section class="flex flex-col gap-1">
          <div class="flex items-center gap-1">
            <span class="text-[10px] font-semibold uppercase tracking-wider text-tertiary">
              Drive folder
            </span>
            <button
              class="flex items-center justify-center text-tertiary transition-colors hover:text-secondary"
              title="Re-connect Google Drive"
              @click="showDrivePrompt = true"
            >
              <Paperclip :size="10" />
            </button>
          </div>

          <div v-if="mirrorBusy" class="text-[11px] italic text-tertiary">
            Loading…
          </div>

          <!-- Not linked -->
          <div
            v-else-if="mirrorStatus && !mirrorStatus.linked"
            class="flex flex-col gap-1.5"
          >
            <p class="text-[10px] leading-relaxed text-tertiary">
              No Drive folder linked. Files in this thread are stored only
              in S3.
            </p>
            <div class="flex items-center gap-1">
              <input
                v-model="linkFolderName"
                type="text"
                placeholder="New Drive folder name"
                class="flex-1 rounded border border-border bg-bg px-2 py-1.5 text-[12px] text-main placeholder-tertiary focus:border-accent/40 focus:outline-none"
                @keydown.enter.prevent="linkFolder()"
              />
              <button
                class="rounded bg-accent px-3 py-1.5 text-[11px] font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
                :disabled="!linkFolderName.trim() || mirrorBusy"
                @click="linkFolder()"
              >
                Link
              </button>
            </div>
          </div>

          <!-- Linked & healthy -->
          <div
            v-else-if="mirrorStatus && mirrorStatus.linked && !mirrorStatus.is_broken"
            class="flex flex-col gap-1.5"
          >
            <div
              class="flex items-center justify-between rounded border border-border bg-bg px-2 py-1.5"
            >
              <div class="flex min-w-0 flex-col leading-tight">
                <span class="truncate text-[12px] text-main" :title="mirrorStatus.folder_name ?? ''">
                  {{ mirrorStatus.folder_name ?? '(unnamed)' }}
                </span>
                <span
                  class="text-[10px] uppercase tracking-wider text-tertiary"
                >
                  {{ mirrorStatus.provider }}
                </span>
              </div>
              <button
                class="rounded px-2 py-1 text-[11px] text-secondary transition-colors hover:bg-hover hover:text-main disabled:opacity-40"
                :disabled="mirrorBusy"
                @click="unlinkFolder"
              >
                Unlink
              </button>
            </div>
            <p class="text-[10px] leading-relaxed text-tertiary">
              Files in <code>input/</code> and <code>output/</code> sync to
              this folder. Renaming the folder in Drive is fine — we
              follow the folder by id.
            </p>
          </div>

          <!-- Linked but broken -->
          <div
            v-else-if="mirrorStatus && mirrorStatus.linked && mirrorStatus.is_broken"
            class="flex flex-col gap-1.5"
          >
            <p
              class="rounded border border-warning/40 bg-warning/10 px-2 py-1.5 text-[11px] leading-relaxed text-warning"
            >
              The linked Drive folder is missing (deleted or trashed).
              Re-link to a new folder to resume sync.
            </p>
            <div class="flex items-center gap-1">
              <input
                v-model="linkFolderName"
                type="text"
                placeholder="New Drive folder name"
                class="flex-1 rounded border border-border bg-bg px-2 py-1.5 text-[12px] text-main placeholder-tertiary focus:border-accent/40 focus:outline-none"
                @keydown.enter.prevent="linkFolder(true)"
              />
              <button
                class="rounded bg-accent px-3 py-1.5 text-[11px] font-semibold text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
                :disabled="!linkFolderName.trim() || mirrorBusy"
                @click="linkFolder(true)"
              >
                Re-link
              </button>
            </div>
          </div>

          <div v-if="mirrorError" class="text-[11px] text-danger">
            {{ mirrorError }}
          </div>
        </section>
      </div>

      <!-- Messages -->
      <div
        v-if="viewMode === 'chat'"
        ref="scrollEl"
        class="flex flex-1 flex-col gap-2 overflow-y-auto rounded-sm border border-border bg-bg-tertiary p-2"
      >
        <!-- Empty state -->
        <div
          v-if="!displayMessages.length"
          class="flex h-full flex-col items-center justify-center gap-3 text-center"
        >
          <img :src="sprihMark" alt="Sprih" class="h-10 w-10 opacity-80" />
          <p class="text-[12px] font-semibold tracking-wide text-secondary">
            How can I help you today?
          </p>
          <p class="text-[11px] text-tertiary">
            Select text in your document and ask me anything
          </p>
        </div>

        <!-- Bubbles -->
        <div
          v-for="item in groupedMessages"
          :key="item.kind === 'human' ? item.msg.id : item.id"
          class="group flex items-end gap-2"
          :class="item.kind === 'human' ? 'user justify-end' : 'assistant'"
        >
          <div
            class="flex min-w-0 flex-col gap-0.5"
            :class="item.kind === 'human' ? 'max-w-[85%] items-end' : 'max-w-[90%] items-start'"
          >
            <span
              class="px-1 text-[10px] font-semibold uppercase tracking-widest"
              :class="item.kind === 'human' ? 'text-secondary' : 'text-accent/60'"
            >
              {{ item.kind === 'human' ? 'you' : 'assistant' }}
            </span>

            <!-- Human message bubble -->
            <template v-if="item.kind === 'human'">
              <div class="flex flex-col items-end gap-1">
                <!-- Attachment chips mirroring the pre-send input UI -->
                <div
                  v-if="humanCtx(item.msg)?.files.length || humanCtx(item.msg)?.synced || humanCtx(item.msg)?.selectedText"
                  class="flex flex-wrap justify-end gap-1"
                >
                  <div
                    v-for="(fname, i) in (humanCtx(item.msg)?.files ?? [])"
                    :key="i"
                    class="flex max-w-[180px] items-center gap-1.5 rounded border border-border bg-bg-tertiary px-2 py-1"
                  >
                    <div class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/15">
                      <FileText :size="11" class="text-accent" />
                    </div>
                    <div class="flex min-w-0 flex-col leading-tight">
                      <span class="truncate text-[10px] font-medium text-main" :title="fname">{{ fname }}</span>
                      <span class="text-[9px] font-semibold uppercase tracking-wider text-tertiary">{{ getFileExt(fname) }}</span>
                    </div>
                  </div>
                  <div
                    v-if="humanCtx(item.msg)?.synced"
                    class="flex max-w-[200px] items-center gap-1.5 rounded border border-accent/30 bg-accent/5 px-2 py-1"
                  >
                    <div class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/15">
                      <EllipsisVertical :size="11" class="text-accent" />
                    </div>
                    <div class="flex min-w-0 flex-col leading-tight">
                      <span class="truncate text-[10px] font-medium text-main">{{ SYNC_PATH }}</span>
                      <span class="text-[9px] font-semibold uppercase tracking-wider text-accent/70">Synced</span>
                    </div>
                  </div>
                  <div
                    v-if="humanCtx(item.msg)?.selectedText"
                    class="flex items-start gap-1.5 rounded border border-border bg-bg-tertiary px-2 py-1.5"
                  >
                    <CornerDownRight :size="10" class="mt-0.5 shrink-0 text-tertiary" />
                    <span class="max-w-[150px] truncate text-[11px] italic leading-relaxed text-tertiary">"{{ humanCtx(item.msg)?.selectedText }}"</span>
                  </div>
                </div>
                <!-- Typed text bubble (omitted when the user sent context only) -->
                <div
                  v-if="(humanCtx(item.msg)?.displayText ?? getMessageText(item.msg)).trim()"
                  class="rounded-sm border border-accent/20 bg-accent/5 px-2 py-1.5 text-[12px] leading-relaxed text-main whitespace-pre-wrap wrap-break-word"
                >
                  {{ (humanCtx(item.msg)?.displayText ?? getMessageText(item.msg)).trim() }}
                </div>
              </div>
            </template>

            <!-- Assistant: tool calls strip (collapsed) then text bubble — single label -->
            <template v-else>
              <details
                v-if="item.calls.length"
                class="w-full rounded border border-border overflow-hidden"
              >
                <summary class="cursor-pointer list-none flex items-center gap-2 px-2.5 py-1.5 hover:bg-hover transition-colors">
                  <span class="flex-1 text-[11px] font-semibold text-secondary">Tool calls</span>
                  <span class="text-[10px] font-semibold text-secondary bg-bg-tertiary border border-border rounded-full px-2 py-0.5">
                    {{ item.calls.length }}
                  </span>
                  <svg
                    class="tool-calls-chevron w-3 h-3 text-secondary transition-transform duration-150"
                    viewBox="0 0 12 12"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  >
                    <path d="M2 4l4 4 4-4" />
                  </svg>
                </summary>
                <div class="flex flex-col divide-y divide-border border-t border-border">
                  <div
                    v-for="tc in item.calls"
                    :key="tc.id"
                    class="relative flex flex-col"
                  >
                    <div class="absolute left-0 top-0 bottom-0 w-[3px] bg-accent/40" />
                    <div
                      class="flex items-center gap-2.5 px-2.5 py-2 cursor-pointer hover:bg-hover transition-colors"
                      @click="toggleToolCallArgs(tc.id)"
                    >
                      <div class="flex-shrink-0 w-6 h-6 rounded-md bg-accent/10 flex items-center justify-center text-accent">
                        <Wrench :size="12" />
                      </div>
                      <div class="flex-1 min-w-0 flex flex-col gap-0.5">
                        <span class="text-[11px] font-medium text-main font-mono truncate">
                          {{ mapped_tc(tc.name, 'name') }}
                        </span>
                        <span class="text-[10px] text-tertiary truncate">
                          {{ mapped_tc(tc.name, 'desc') }}
                        </span>
                      </div>
                    </div>
                    <div
                      v-if="expandedToolCalls[tc.id]"
                      class="pl-11 pr-2.5 pb-2 pt-1.5 flex flex-col gap-1.5 border-t border-border"
                    >
                      <template v-if="toolCallArgs(tc.name, tc.args).length">
                        <div
                          v-for="arg in toolCallArgs(tc.name, tc.args)"
                          :key="arg.field"
                          class="flex items-baseline gap-1.5 min-w-0"
                        >
                          <span class="flex-shrink-0 text-[9px] font-semibold font-mono uppercase tracking-wider text-secondary">{{ arg.field }}</span>
                          <span class="text-[10px] text-tertiary" :class="arg.truncate ? 'truncate' : ''">{{ arg.value }}</span>
                        </div>
                      </template>
                      <span v-else class="text-[10px] italic text-tertiary">No args</span>
                    </div>
                  </div>
                </div>
              </details>

              <div
                v-if="item.msg && renderSegments(item.msg).length"
                class="rounded-sm border border-border bg-bg-secondary px-2 py-1.5 text-[12px] leading-relaxed text-main wrap-break-word"
              >
                <template v-for="(seg, idx) in renderSegments(item.msg)" :key="idx">
                  <div
                    v-if="seg.type === 'text'"
                    v-html="markdownToHtml(seg.text)"
                    class="ai-markdown"
                  />
                  <details
                    v-else
                    class="mt-1 rounded border border-border bg-bg-tertiary"
                  >
                    <summary
                      class="cursor-pointer list-none px-2 py-1 text-[10px] font-semibold uppercase tracking-widest text-tertiary"
                    >
                      Thought process
                    </summary>
                    <pre
                      class="m-0 whitespace-pre-wrap wrap-break-word px-2 py-1 text-[11px] text-tertiary"
                    >{{ seg.text.trim() }}</pre>
                  </details>
                </template>
              </div>

              <div
                v-if="item.msg && cleanText(item.msg)"
                class="flex gap-0.5 opacity-0 transition-opacity group-hover:opacity-100"
              >
                <button
                  class="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-secondary transition-colors hover:bg-hover hover:text-main disabled:cursor-not-allowed disabled:opacity-40"
                  title="Replace selection"
                  :disabled="!isWordContext"
                  @click="insertToDoc(item.msg, 'replace')"
                >
                  <FileText :size="9" />
                  <span>Replace</span>
                </button>
                <button
                  class="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-secondary transition-colors hover:bg-hover hover:text-main disabled:cursor-not-allowed disabled:opacity-40"
                  title="Append after selection"
                  :disabled="!isWordContext"
                  @click="insertToDoc(item.msg, 'append')"
                >
                  <Plus :size="9" />
                  <span>Append</span>
                </button>
                <button
                  class="flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] text-secondary transition-colors hover:bg-hover hover:text-main"
                  title="Copy to clipboard"
                  @click="copyToClipboard(item.msg)"
                >
                  <Copy :size="9" />
                  <span>{{ copiedId === item.msg.id ? 'Copied' : 'Copy' }}</span>
                </button>
              </div>
            </template>
          </div>
        </div>

        <div v-if="streaming && !lastIsStreamingAi" class="text-[11px] italic text-tertiary">
          agent is thinking…
        </div>
        <div v-if="error" class="text-[11px] text-danger">{{ error }}</div>
      </div>

      <!-- Input -->
      <div
        v-if="viewMode === 'chat'"
        class="flex flex-col gap-1 rounded-sm border border-border bg-bg-secondary p-1.5"
      >
        <!-- Pending-file chips + sync chip -->
        <div
          v-if="pendingFiles.length || syncArmed"
          class="flex flex-wrap gap-1"
        >
          <div
            v-for="(pf, idx) in pendingFiles"
            :key="idx"
            class="flex max-w-[180px] items-center gap-1.5 rounded border border-border bg-bg-tertiary px-2 py-1"
          >
            <div
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/15"
            >
              <FileText :size="11" class="text-accent" />
            </div>
            <div class="flex min-w-0 flex-col leading-tight">
              <span
                class="truncate text-[10px] font-medium text-main"
                :title="pf.file.name"
              >
                {{ pf.file.name }}
              </span>
              <span
                class="text-[9px] font-semibold uppercase tracking-wider text-tertiary"
              >
                {{ getFileExt(pf.file.name) }}
              </span>
            </div>
            <button
              class="ml-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-hover text-tertiary transition-colors hover:bg-bg-tertiary hover:text-main"
              :title="`Remove ${pf.file.name}`"
              @click="removePendingFile(idx)"
            >
              <X :size="8" />
            </button>
          </div>

          <div
            v-if="syncArmed"
            class="flex max-w-[200px] items-center gap-1.5 rounded border border-accent/30 bg-accent/5 px-2 py-1"
          >
            <div
              class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/15"
            >
              <EllipsisVertical :size="11" class="text-accent" />
            </div>
            <div class="flex min-w-0 flex-col leading-tight">
              <span
                class="truncate text-[10px] font-medium text-main"
                :title="SYNC_PATH"
              >
                {{ SYNC_PATH }}
              </span>
              <span
                class="text-[9px] font-semibold uppercase tracking-wider text-accent/70"
              >
                Sync on send
              </span>
            </div>
            <button
              class="ml-0.5 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-hover text-tertiary transition-colors hover:bg-bg-tertiary hover:text-main"
              title="Disarm sync"
              @click="syncArmed = false"
            >
              <X :size="8" />
            </button>
          </div>
        </div>

        <!-- Sync status (transient) -->
        <div
          v-if="syncStatus"
          class="text-[10px] italic text-tertiary"
        >
          {{ syncStatus }}
        </div>

        <!-- Selected-text preview chip -->
        <div
          v-if="selectedTextPreview"
          class="flex items-start gap-1.5 rounded border border-border bg-bg-tertiary px-2 py-1.5"
        >
          <CornerDownRight
            :size="10"
            class="mt-0.5 shrink-0 text-tertiary"
          />
          <span
            class="flex-1 truncate text-[11px] italic leading-relaxed text-tertiary"
          >
            "{{ selectedTextPreview }}"
          </span>
          <button
            class="shrink-0 text-tertiary transition-colors hover:text-secondary"
            @click="dismissSelectedTextPreview"
          >
            <X :size="9" />
          </button>
        </div>

        <div
          class="flex items-end gap-0.5 rounded border border-border bg-bg-tertiary pl-1 pr-2 py-1 transition-colors focus-within:border-accent/40"
        >
          <div ref="attachMenuRef" class="relative shrink-0">
            <button
              class="flex h-5 w-5 items-center justify-center rounded transition-colors disabled:opacity-40"
              :class="
                syncArmed
                  ? 'text-accent hover:bg-accent/15'
                  : 'text-tertiary hover:bg-hover hover:text-main'
              "
              title="More options"
              :disabled="streaming"
              @click.stop="attachMenuOpen = !attachMenuOpen"
            >
              <EllipsisVertical :size="12" />
            </button>

            <div
              v-if="attachMenuOpen"
              class="absolute bottom-full left-0 z-10 mb-1 flex min-w-[160px] flex-col rounded border border-border bg-bg-secondary py-0.5 shadow-md"
            >
              <button
                class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] text-main transition-colors hover:bg-hover"
                @click="openFilePicker(); attachMenuOpen = false"
              >
                <Paperclip :size="11" class="shrink-0 text-tertiary" />
                Add files or photos
              </button>
              <button
                class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] transition-colors hover:bg-hover disabled:cursor-not-allowed disabled:opacity-40"
                :class="syncArmed ? 'text-accent' : 'text-main'"
                :disabled="!isWordContext"
                @click="toggleSync(); attachMenuOpen = false"
              >
                <Upload
                  :size="11"
                  class="shrink-0"
                  :class="syncArmed ? 'text-accent' : 'text-tertiary'"
                />
                {{ syncArmed ? 'Send Document (armed)' : 'Send Document' }}
              </button>
              <button
                class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[11px] text-main transition-colors hover:bg-hover disabled:opacity-40"
                :disabled="pulling || !isWordContext"
                @click="pullIntoDocument(); attachMenuOpen = false"
              >
                <Download :size="11" class="shrink-0 text-tertiary" />
                Get Document
              </button>
            </div>
          </div>

          <textarea
            ref="inputTextarea"
            v-model="input"
            :placeholder="streaming ? 'Streaming…' : 'Ask the agent…'"
            rows="1"
            :disabled="streaming"
            class="flex-1 resize-none bg-transparent text-[12px] leading-relaxed text-main placeholder-tertiary focus:outline-none disabled:opacity-50"
            @keydown.enter.exact.prevent="onSubmit"
            @input="adjustTextareaHeight"
          />

          <button
            v-if="streaming"
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-danger/80 text-white transition-colors hover:bg-danger"
            title="Stop"
            @click="stopGeneration"
          >
            <Square :size="10" />
          </button>
          <button
            v-else
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent text-on-accent transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-30"
            title="Send"
            :disabled="!input.trim() && pendingFiles.length === 0 && !syncArmed && !selectedTextPreview"
            @click="onSubmit"
          >
            <Send :size="10" />
          </button>
        </div>

        <!-- Hidden file input — driven by the paperclip button above -->
        <input
          ref="fileInput"
          type="file"
          multiple
          accept="*/*"
          class="hidden"
          @change="onFilesPicked"
        />
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import {
  ArrowLeft,
  Copy,
  CornerDownRight,
  Download,
  EllipsisVertical,
  FileText,
  History,
  Moon,
  Paperclip,
  Pencil,
  Plus,
  Send,
  Square,
  Sun,
  Upload,
  Wrench,
  X,
} from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

import { insertFormattedResult } from '@/api/common'
import { BASE_URL } from '@/api/config'
import sprihLogo from '@/assets/brand/sprih-logo.png'
import sprihMark from '@/assets/brand/sprih-mark.png'
import {
  readFile,
  SYNC_PATH,
  uploadFiles,
  UPLOAD_FOLDER,
  writeFile,
  type WriteResult,
} from '@/api/files'
import {
  getMirrorStatus,
  linkMirror,
  unlinkMirror,
  type MirrorStatus,
} from '@/api/mirror'
import { streamRun } from '@/api/runs'
import {
  createThread,
  getThreadState,
  listThreads,
  updateThreadMetadata,
  type AgentMessage,
  type ThreadSummary,
} from '@/api/threads'
import { htmlToMarkdown, markdownToHtml } from '@/utils/mdFormatter'
import toolMap from '@/mappings/tool_mapped.json'
import toolArgsMap from '@/mappings/tool_args_mapped.json'

function mapped_tc(name: string, field: 'name' | 'desc'): string {
  const entry = (toolMap as Record<string, { name: string; description: string }>)[name]
  if (!entry) return field === 'name' ? name : ''
  return field === 'name' ? entry.name : entry.description
}

const expandedToolCalls = reactive<Record<string, boolean>>({})

function toggleToolCallArgs(id: string) {
  expandedToolCalls[id] = !expandedToolCalls[id]
}

type ArgEntry = { field: string; value: string; truncate: boolean }

function toolCallArgs(name: string, args: Record<string, unknown>): ArgEntry[] {
  const entry = (
    toolArgsMap as Array<{ tc_name: string; tc_params: Array<{ field: string; truncate?: boolean }> }>
  ).find((e) => e.tc_name === name)
  const paramMap = entry
    ? new Map(entry.tc_params.map((p) => [p.field, p.truncate ?? false]))
    : null
  return Object.entries(args)
    .filter(([k]) => !paramMap || paramMap.has(k))
    .map(([k, v]) => ({
      field: k,
      value: typeof v === 'string' ? v : JSON.stringify(v),
      truncate: paramMap?.get(k) ?? false,
    }))
}

const DRIVE_PROMPT_KEY = 'sprih.drivePromptSeen'
const showDrivePrompt = ref(localStorage.getItem(DRIVE_PROMPT_KEY) !== 'true')
const driveAuthUrl = ref<string | null>(null)
const driveConnectError = ref<string | null>(null)

function dismissDrivePrompt() {
  showDrivePrompt.value = false
  localStorage.setItem(DRIVE_PROMPT_KEY, 'true')
}

async function onDrivePromptYes() {
  dismissDrivePrompt()
  await sendConnectionRequest()
}

async function sendConnectionRequest() {
  driveConnectError.value = null
  try {
    const res = await fetch(`${BASE_URL}/auth/google/start`, {
      headers: { accept: 'application/json' },
    })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    const { authorize_url } = await res.json()

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const officeUi = (window as any).Office?.context?.ui
    if (typeof officeUi?.openBrowserWindow === 'function') {
      officeUi.openBrowserWindow(authorize_url)
    } else {
      const opened = window.open(authorize_url, '_blank')
      if (!opened) {
        driveAuthUrl.value = authorize_url
        return
      }
    }

    showFolderIdPrompt.value = true
  } catch (e) {
    driveConnectError.value = e instanceof Error ? e.message : String(e)
  }
}

const showFolderIdPrompt = ref(false)
const folderIdInput = ref('')

function onFolderIdOk() {
  const id = folderIdInput.value.trim()
  if (!id) return
  showFolderIdPrompt.value = false
  folderIdInput.value = ''
  handleFolderId(id)
}

const folderIdSuccess = ref(false)

async function handleFolderId(folderId: string) {
  const res = await fetch(`${BASE_URL}/auth/google/parent-folder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', accept: 'application/json' },
    body: JSON.stringify({ drive_parent_folder_id: folderId }),
  })
  if (res.ok) folderIdSuccess.value = true
}

const THREAD_KEY = 'sprih.threadId'
const TITLE_KEY = 'sprih.threadTitle'
const DARK_KEY = 'sprih.darkMode'

const darkMode = ref(localStorage.getItem(DARK_KEY) === 'true')

function applyDarkMode(on: boolean) {
  document.documentElement.classList.toggle('dark', on)
}

function toggleDarkMode() {
  darkMode.value = !darkMode.value
  applyDarkMode(darkMode.value)
  localStorage.setItem(DARK_KEY, String(darkMode.value))
}

applyDarkMode(darkMode.value)

type ViewMode = 'chat' | 'history' | 'editThread'
const THINK_TAG = '<think>'
const THINK_TAG_END = '</think>'

interface RenderSegment {
  type: 'text' | 'think'
  text: string
}

const threadId = ref<string | null>(localStorage.getItem(THREAD_KEY))
const threadTitle = ref<string | null>(localStorage.getItem(TITLE_KEY))
const messages = ref<AgentMessage[]>([])
const input = ref('')
const streaming = ref(false)
const error = ref<string | null>(null)
const selectedTextPreview = ref('')
const dismissedSelectedText = ref('')
const copiedId = ref<string | null>(null)
const scrollEl = ref<HTMLElement | null>(null)
const inputTextarea = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const abortController = ref<AbortController | null>(null)

// View-mode state — header History button toggles between chat + history.
const viewMode = ref<ViewMode>('chat')

// History panel state.
const historyThreads = ref<ThreadSummary[]>([])
const historyLoading = ref(false)
const historyError = ref<string | null>(null)

// Edit thread panel state.
const editingThread = ref<ThreadSummary | null>(null)
const editTitle = ref('')
const savingTitle = ref(false)
const mirrorStatus = ref<MirrorStatus | null>(null)
const mirrorBusy = ref(false)
const mirrorError = ref<string | null>(null)
const linkFolderName = ref('')

const headerSubtitle = computed(() => {
  if (viewMode.value === 'history') return 'select a thread'
  if (viewMode.value === 'editThread')
    return editingThread.value?.title ?? 'editing thread'
  if (threadTitle.value) return threadTitle.value
  if (threadId.value) return `thread ${threadId.value.slice(0, 8)}…`
  return 'no thread yet'
})

interface PendingFile {
  file: File
}
const pendingFiles = ref<PendingFile[]>([])

// Sync state. ``syncArmed`` arms a "push the current Word body" action that
// fires on the next send (matches Sanvi's flow — defers the actual upload
// to send time so the user can compose a message about what they want done
// with the synced doc and ship both together).
const syncArmed = ref(false)
const pulling = ref(false)
const syncStatus = ref<string | null>(null)

const attachMenuOpen = ref(false)
const attachMenuRef = ref<HTMLElement | null>(null)
const isWordContext = ref(false)

// Per-message context for human bubbles sent this session.
// Separates what the user typed from the internal backend-facing suffixes.
interface HumanMsgContext {
  displayText: string
  files: string[]
  synced: boolean
  selectedText: string
}
const humanMsgContext = reactive<Record<string, HumanMsgContext>>({})

function closeAttachMenu(e: MouseEvent) {
  if (attachMenuRef.value && !attachMenuRef.value.contains(e.target as Node)) {
    attachMenuOpen.value = false
  }
}

// Visible messages: human always shown; AI shown when it has real text or tool calls.
// Uses getMessageText (not !!m.content) so array-typed content is handled correctly.
// Tool/system messages are excluded — they are never directly rendered.
const displayMessages = computed(() =>
  messages.value.filter((m) => {
    if (m.type === 'human') return true
    if (m.type === 'ai') return !!getMessageText(m) || !!m.tool_calls?.length
    return false
  }),
)

type ToolCallEntry = { id: string; name: string; args: Record<string, unknown> }
interface HumanItem { kind: 'human'; msg: AgentMessage }
interface AssistantItem { kind: 'assistant'; id: string; calls: ToolCallEntry[]; msg: AgentMessage | null }
type DisplayItem = HumanItem | AssistantItem

// Groups consecutive AI planning steps (tool-calls-only) into a single AssistantItem.
// Operates on displayMessages so tool/system messages are already excluded.
const groupedMessages = computed<DisplayItem[]>(() => {
  const items: DisplayItem[] = []
  let pendingCalls: ToolCallEntry[] = []
  let groupId = ''

  for (const m of displayMessages.value) {
    if (m.type === 'human') {
      if (pendingCalls.length) {
        items.push({ kind: 'assistant', id: groupId, calls: pendingCalls, msg: null })
        pendingCalls = []
        groupId = ''
      }
      items.push({ kind: 'human', msg: m })
    } else {
      // All non-human messages in displayMessages are type 'ai'.
      // Two independent checks — a message can accumulate tool calls AND flush text.
      if (m.tool_calls?.length) {
        if (!groupId) groupId = m.id
        pendingCalls = [...pendingCalls, ...m.tool_calls]
      }
      if (getMessageText(m)) {
        // Any AI message with real text always produces a visible AssistantItem,
        // carrying whatever tool calls have accumulated so far (including its own).
        items.push({ kind: 'assistant', id: groupId || m.id, calls: pendingCalls, msg: m })
        pendingCalls = []
        groupId = ''
      }
    }
  }

  if (pendingCalls.length) {
    items.push({ kind: 'assistant', id: groupId, calls: pendingCalls, msg: null })
  }

  return items
})

// Last visible AI message is currently streaming if its content is non-empty
// — used to suppress the "agent is thinking…" line once tokens land.
const lastIsStreamingAi = computed(() => {
  if (!streaming.value) return false
  const last = groupedMessages.value.at(-1)
  if (!last || last.kind === 'human') return false
  return !!last.msg?.content
})

function getMessageText(m: AgentMessage): string {
  if (typeof m.content === 'string') return m.content
  if (Array.isArray(m.content)) {
    return (m.content as Array<string | { text?: string }>)
      .map((part) =>
        typeof part === 'string' ? part : (part?.text ?? ''),
      )
      .join('')
  }
  return ''
}

function cleanText(m: AgentMessage): string {
  const re = new RegExp(`${THINK_TAG}[\\s\\S]*?${THINK_TAG_END}`, 'g')
  return getMessageText(m).replace(re, '').trim()
}

function humanCtx(m: AgentMessage): HumanMsgContext | null {
  return humanMsgContext[getMessageText(m)] ?? null
}

// Split AI content into [text, think, text, …] segments so we can render
// `<think>…</think>` blocks as collapsibles instead of dumping them in the
// bubble. Anthropic models don't emit these, but we keep the splitter for
// when the agent surfaces tool reasoning or other model providers.
function renderSegments(m: AgentMessage): RenderSegment[] {
  const text = getMessageText(m)
  if (!text) return []
  const segments: RenderSegment[] = []
  let cursor = 0
  while (cursor < text.length) {
    const start = text.indexOf(THINK_TAG, cursor)
    if (start === -1) {
      segments.push({ type: 'text', text: text.slice(cursor) })
      break
    }
    if (start > cursor)
      segments.push({ type: 'text', text: text.slice(cursor, start) })
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
  return segments.filter((s) => s.text)
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
    // Stale thread id from a wiped backend → drop and start fresh.
    console.warn('Hydrate failed, resetting thread:', e)
    localStorage.removeItem(THREAD_KEY)
    threadId.value = null
  }
}

async function onSubmit() {
  const typed = input.value.trim()
  // Allow sending with no text iff the user attached a file or armed a
  // sync — either the file-reference or sync suffix becomes the body.
  if (
    (!typed && pendingFiles.value.length === 0 && !syncArmed.value && !selectedTextPreview.value) ||
    streaming.value
  )
    return
  input.value = ''
  adjustTextareaHeight()
  error.value = null
  streaming.value = true
  abortController.value = new AbortController()

  // --- Ensure a thread exists FIRST ---------------------------------------
  // Files and sync are scoped to a thread, so we materialise it before
  // anything that needs the thread_id. ``ensureThread`` is a no-op when a
  // thread is already pinned in localStorage.
  let tid: string
  try {
    tid = await ensureThread()
  } catch (e) {
    streaming.value = false
    abortController.value = null
    error.value = `Thread setup failed: ${e instanceof Error ? e.message : String(e)}`
    return
  }

  // --- Upload attachments ---------------------------------------------------
  // We upload eagerly (not in parallel with the stream) so the resulting
  // storage keys can be cited in the message text the agent receives.
  let uploaded: WriteResult[] = []
  const filesToUpload = pendingFiles.value.map((p) => p.file)
  if (filesToUpload.length) {
    try {
      uploaded = await uploadFiles(tid, filesToUpload)
      pendingFiles.value = []
    } catch (e) {
      streaming.value = false
      abortController.value = null
      error.value = `Upload failed: ${e instanceof Error ? e.message : String(e)}`
      return
    }
  }

  // --- Push current doc if sync was armed ---------------------------------
  let didSync = false
  if (syncArmed.value) {
    try {
      const markdown = await readCurrentDocument()
      await writeFile(tid, SYNC_PATH, markdown)
      didSync = true
      syncArmed.value = false
    } catch (e) {
      streaming.value = false
      abortController.value = null
      error.value = `Sync failed: ${e instanceof Error ? e.message : String(e)}`
      return
    }
  }

  // --- Compose the outgoing message ---------------------------------------
  let text = buildMessageWithFileReferences(typed, uploaded)
  if (didSync) text = text ? `${text}\n\n${SYNC_SUFFIX}` : SYNC_SUFFIX
  const selectedText = selectedTextPreview.value
  if (selectedText) {
    text = text ? `${text}\n\nSelected Text: ${selectedText}` : `Selected Text: ${selectedText}`
    selectedTextPreview.value = ''
    dismissedSelectedText.value = ''
  }

  // Store bubble context — typed text + attachment metadata — keyed by the
  // full backend message so both the optimistic and canonical bubbles resolve it.
  humanMsgContext[text] = {
    displayText: typed,
    files: uploaded.map((u) => u.key.split('/').pop() ?? u.key),
    synced: didSync,
    selectedText,
  }

  // Optimistic: render the user's message immediately. The first `values`
  // event from the backend will replace the whole list with canonical state.
  messages.value = [
    ...messages.value,
    { type: 'human', id: `user-${Date.now()}`, content: text },
  ]
  scrollToBottom()

  try {
    for await (const evt of streamRun({
      threadId: tid,
      message: text,
      clientType: isWordContext.value ? 'word' : 'browser',
      signal: abortController.value.signal,
    })) {
      if (evt.event === 'values') {
        messages.value = evt.data.messages
        scrollToBottom()
      } else if (evt.event === 'error') {
        error.value = `${evt.data.error}: ${evt.data.message}`
      }
    }
    // Auto-title: first time we successfully stream against a thread
    // with no title set, derive one from the typed prompt and PATCH the
    // metadata so the history list shows something recognisable. Fire-
    // and-forget — a network blip on PATCH isn't worth surfacing.
    if (!threadTitle.value && typed) {
      const auto = deriveAutoTitle(typed)
      threadTitle.value = auto
      localStorage.setItem(TITLE_KEY, auto)
      void updateThreadMetadata(tid, { title: auto }).catch((e) => {
        console.warn('Auto-title PATCH failed:', e)
      })
    }
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') {
      // user-initiated stop, no error UI
    } else {
      error.value = e instanceof Error ? e.message : String(e)
    }
  } finally {
    streaming.value = false
    abortController.value = null
  }
}

const AUTO_TITLE_MAX = 60

// Derive a thread title from a user message: collapse whitespace and
// truncate to 60 chars with an ellipsis. Mirrors the server-side
// fallback in ``api/threads.ts:deriveTitle`` so both views agree on
// what an auto-title looks like.
function deriveAutoTitle(text: string): string {
  const collapsed = text.replace(/\s+/g, ' ').trim()
  return collapsed.length > AUTO_TITLE_MAX
    ? collapsed.slice(0, AUTO_TITLE_MAX - 1) + '…'
    : collapsed
}

// Append a "reference file" suffix to the user's typed text so the agent
// knows where to find the attached files. Singular/plural copy chosen at
// runtime based on how many files were uploaded.
function buildMessageWithFileReferences(
  typed: string,
  uploaded: WriteResult[],
): string {
  if (uploaded.length === 0) return typed
  const lines = uploaded.map((u) => `- ${u.key}`).join('\n')
  const suffix =
    uploaded.length === 1
      ? `I have put the reference file at this location: ${uploaded[0].key}`
      : `I have put the reference files at these locations:\n${lines}`
  return typed ? `${typed}\n\n${suffix}` : suffix
}

// ── File picker ─────────────────────────────────────────────────────────

function openFilePicker() {
  fileInput.value?.click()
}

function onFilesPicked(evt: Event) {
  const target = evt.target as HTMLInputElement
  const picked = Array.from(target.files ?? [])
  for (const f of picked) pendingFiles.value.push({ file: f })
  // Reset so the same file can be picked again after removal.
  target.value = ''
}

function removePendingFile(idx: number) {
  pendingFiles.value.splice(idx, 1)
}

function getFileExt(filename: string): string {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.at(-1)!.toUpperCase() : 'FILE'
}

// ── Word document sync ──────────────────────────────────────────────────

const SYNC_SUFFIX = `[Sync]: I have modified our shared file (${SYNC_PATH}) with my current document. Check.`

function toggleSync() {
  syncArmed.value = !syncArmed.value
}

// Read the current Word doc body, prefer HTML-via-markdown so basic
// formatting (headings, lists, bold) survives the round-trip; fall back
// to plain text if the HTML path throws.
async function readCurrentDocument(): Promise<string> {
  return Word.run(async (ctx) => {
    const body = ctx.document.body
    try {
      const htmlResult = body.getHtml()
      await ctx.sync()
      return htmlToMarkdown(htmlResult.value)
    } catch {
      body.load('text')
      await ctx.sync()
      return body.text ?? ''
    }
  })
}

async function pullIntoDocument() {
  if (pulling.value) return
  // Pulling implies the thread exists — if there isn't one yet there's
  // nothing to pull. Surface that explicitly rather than 404'ing the
  // user with a confusing backend error.
  if (!threadId.value) {
    syncStatus.value = 'Nothing to pull yet — start a conversation first.'
    setTimeout(() => {
      syncStatus.value = null
    }, 3000)
    return
  }
  pulling.value = true
  syncStatus.value = null
  try {
    const doc = await readFile(threadId.value, SYNC_PATH)
    // Replace the entire Word body. ``insertFormattedResult`` tries the
    // markdown-aware writer first and falls back to plain text.
    const mode = ref<'replaceAll'>('replaceAll')
    await insertFormattedResult(doc.content, mode)
    syncStatus.value = `Pulled ${doc.key}`
  } catch (e) {
    syncStatus.value =
      e instanceof Error
        ? `Pull failed: ${e.message}`
        : `Pull failed: ${String(e)}`
  } finally {
    pulling.value = false
    setTimeout(() => {
      syncStatus.value = null
    }, 3000)
  }
}

function stopGeneration() {
  abortController.value?.abort()
}

// Reset chat-view state. Used after creating a fresh thread or loading
// a different one from history — drops compose-side leftovers but does
// NOT touch ``threadId`` (the caller decides what's active).
function resetChatState() {
  messages.value = []
  error.value = null
  selectedTextPreview.value = ''
  dismissedSelectedText.value = ''
  pendingFiles.value = []
  syncArmed.value = false
  syncStatus.value = null
}

// Header-button handler — flip into the requested view, or back to chat
// if the same button is pressed again.
function toggleView(target: 'history') {
  if (streaming.value) return
  if (viewMode.value === target) {
    viewMode.value = 'chat'
    return
  }
  viewMode.value = target
  if (target === 'history') refreshHistory()
}

// "+" button — drop the current thread and let the next send create a
// fresh one. No title prompt; the title is auto-derived from the first
// message and can be edited later from the history panel.
function newChat() {
  if (streaming.value) return
  localStorage.removeItem(THREAD_KEY)
  localStorage.removeItem(TITLE_KEY)
  threadId.value = null
  threadTitle.value = null
  resetChatState()
  viewMode.value = 'chat'
}

async function refreshHistory() {
  historyLoading.value = true
  historyError.value = null
  try {
    historyThreads.value = await listThreads(50)
  } catch (e) {
    historyError.value =
      e instanceof Error ? e.message : `Load failed: ${String(e)}`
  } finally {
    historyLoading.value = false
  }
}

// ── Edit thread panel ───────────────────────────────────────────────────

async function openEditThread(t: ThreadSummary) {
  if (streaming.value) return
  editingThread.value = t
  editTitle.value = t.title ?? ''
  linkFolderName.value = ''
  mirrorError.value = null
  mirrorStatus.value = null
  viewMode.value = 'editThread'
  mirrorBusy.value = true
  try {
    mirrorStatus.value = await getMirrorStatus(t.thread_id)
  } catch (e) {
    mirrorError.value =
      e instanceof Error ? e.message : `Status fetch failed: ${String(e)}`
  } finally {
    mirrorBusy.value = false
  }
}

function closeEditThread() {
  editingThread.value = null
  mirrorStatus.value = null
  mirrorError.value = null
  linkFolderName.value = ''
  viewMode.value = 'history'
  // Refresh history so a renamed thread shows the new title.
  refreshHistory()
}

async function saveTitle() {
  const t = editingThread.value
  if (!t) return
  const next = editTitle.value.trim()
  if (!next || next === (t.title ?? '') || savingTitle.value) return
  savingTitle.value = true
  try {
    await updateThreadMetadata(t.thread_id, { title: next })
    // Mirror updated title locally so the close handler's refresh is
    // smooth even on slow networks.
    editingThread.value = { ...t, title: next }
    if (threadId.value === t.thread_id) {
      threadTitle.value = next
      localStorage.setItem(TITLE_KEY, next)
    }
  } catch (e) {
    mirrorError.value =
      e instanceof Error ? e.message : `Rename failed: ${String(e)}`
  } finally {
    savingTitle.value = false
  }
}

async function linkFolder(ifBroken = false) {
  const t = editingThread.value
  const name = linkFolderName.value.trim()
  if (!t || !name || mirrorBusy.value) return
  mirrorBusy.value = true
  mirrorError.value = null
  try {
    await linkMirror(t.thread_id, name, ifBroken)
    mirrorStatus.value = await getMirrorStatus(t.thread_id)
    linkFolderName.value = ''
  } catch (e) {
    mirrorError.value =
      e instanceof Error ? e.message : `Link failed: ${String(e)}`
  } finally {
    mirrorBusy.value = false
  }
}

async function unlinkFolder() {
  const t = editingThread.value
  if (!t || mirrorBusy.value) return
  mirrorBusy.value = true
  mirrorError.value = null
  try {
    await unlinkMirror(t.thread_id)
    mirrorStatus.value = await getMirrorStatus(t.thread_id)
  } catch (e) {
    mirrorError.value =
      e instanceof Error ? e.message : `Unlink failed: ${String(e)}`
  } finally {
    mirrorBusy.value = false
  }
}

async function loadThread(t: ThreadSummary) {
  if (streaming.value) return
  threadId.value = t.thread_id
  threadTitle.value = t.title
  localStorage.setItem(THREAD_KEY, t.thread_id)
  if (t.title) localStorage.setItem(TITLE_KEY, t.title)
  else localStorage.removeItem(TITLE_KEY)
  resetChatState()
  viewMode.value = 'chat'
  await hydrate()
}

// The backend emits UTC ISO strings without a 'Z' marker (e.g.
// ``2026-05-07T12:32:36``). Per ECMA-262 those would be parsed as
// LOCAL time, so a thread created moments ago in IST would appear
// 5h30m old. Treat naive strings as UTC explicitly.
function parseTimestamp(iso: string): Date {
  const hasTz = /Z$|[+-]\d{2}:?\d{2}$/.test(iso)
  return new Date(hasTz ? iso : iso + 'Z')
}

// Render an updated_at timestamp as a compact relative string like
// "2m ago" / "3h ago" / "yesterday" / "Mar 14". Just enough fidelity
// to scan a list at a glance — falls back to a calendar date past a week.
function formatRelativeTime(iso: string): string {
  const date = parseTimestamp(iso)
  const then = date.getTime()
  if (Number.isNaN(then)) return ''
  const now = Date.now()
  const diff = Math.max(0, now - then)
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return 'just now'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.floor(hr / 24)
  if (day === 1) return 'yesterday'
  if (day < 7) return `${day}d ago`
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  })
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  })
}

function adjustTextareaHeight() {
  const el = inputTextarea.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 120)}px`
}

// ── Word document interop ───────────────────────────────────────────────

const insertTypeRef = ref<'replace' | 'append'>('replace')

async function insertToDoc(m: AgentMessage, mode: 'replace' | 'append') {
  insertTypeRef.value = mode
  await insertFormattedResult(cleanText(m), insertTypeRef)
}

async function copyToClipboard(m: AgentMessage) {
  try {
    await navigator.clipboard.writeText(cleanText(m))
    copiedId.value = m.id
    setTimeout(() => {
      if (copiedId.value === m.id) copiedId.value = null
    }, 1200)
  } catch (e) {
    console.warn('Clipboard copy failed:', e)
  }
}

// Read the current Word selection so the user has visible context for
// what their next message will reference. Only works when running inside
// Word (Office.context.document is undefined in plain browser).
async function fetchSelectedTextPreview() {
  try {
    const text = await Word.run(async (ctx) => {
      const range = ctx.document.getSelection()
      range.load('text')
      await ctx.sync()
      return range.text?.trim() ?? ''
    })
    if (!text) {
      selectedTextPreview.value = ''
      dismissedSelectedText.value = ''
    } else if (text !== dismissedSelectedText.value) {
      dismissedSelectedText.value = ''
      selectedTextPreview.value = text
    }
  } catch {
    selectedTextPreview.value = ''
  }
}

function dismissSelectedTextPreview() {
  dismissedSelectedText.value = selectedTextPreview.value
  selectedTextPreview.value = ''
}

let selectionHandlerInstalled = false

onMounted(() => {
  document.addEventListener('click', closeAttachMenu)
  hydrate()
  // Office.context.document exists only inside Word, not in plain browsers.
  // Guard the handler registration so the page still loads at /index.html.
  try {
    const Office = (window as unknown as { Office?: typeof globalThis.Office })
      .Office
    if (Office?.context?.document?.addHandlerAsync) {
      isWordContext.value = true
      Office.context.document.addHandlerAsync(
        Office.EventType.DocumentSelectionChanged,
        fetchSelectedTextPreview,
      )
      selectionHandlerInstalled = true
      // Prime once on mount so the chip appears if the user already had a selection.
      fetchSelectedTextPreview()
    }
  } catch (e) {
    console.warn('Selection handler not available (running outside Word):', e)
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', closeAttachMenu)
  abortController.value?.abort()
  if (selectionHandlerInstalled) {
    try {
      const Office = (
        window as unknown as { Office?: typeof globalThis.Office }
      ).Office
      Office?.context?.document?.removeHandlerAsync?.(
        Office.EventType.DocumentSelectionChanged,
      )
    } catch {
      /* ignore */
    }
  }
})
</script>

<style>
details[open] .tool-calls-chevron {
  transform: rotate(180deg);
}

/* AI message markdown — compact, dark-mode-tuned. */
.ai-markdown p {
  margin: 0.15em 0;
}
.ai-markdown h1,
.ai-markdown h2 {
  font-size: 1em;
  font-weight: 700;
  margin: 0.4em 0 0.15em;
}
.ai-markdown h3,
.ai-markdown h4,
.ai-markdown h5,
.ai-markdown h6 {
  font-weight: 600;
  margin: 0.3em 0 0.1em;
}
.ai-markdown strong {
  font-weight: 700;
}
.ai-markdown em {
  font-style: italic;
}
.ai-markdown a {
  color: var(--color-accent);
  text-decoration: underline;
}
.ai-markdown code {
  font-family: 'Consolas', 'Menlo', monospace;
  font-size: 0.9em;
  background: var(--color-code-bg);
  border-radius: 3px;
  padding: 0 3px;
}
.ai-markdown pre {
  background: var(--color-background-tertiary);
  border-radius: 4px;
  padding: 6px 8px;
  margin: 0.3em 0;
  overflow-x: auto;
}
.ai-markdown pre code {
  background: none;
  padding: 0;
  font-size: 0.88em;
}
.ai-markdown ul {
  list-style: disc;
  padding-left: 1.2em;
  margin: 0.2em 0;
}
.ai-markdown ol {
  list-style: decimal;
  padding-left: 1.2em;
  margin: 0.2em 0;
}
.ai-markdown li {
  margin: 0.1em 0;
}
.ai-markdown blockquote {
  border-left: 2px solid color-mix(in srgb, var(--color-accent) 50%, transparent);
  padding-left: 0.5em;
  color: var(--color-text-tertiary);
  font-style: italic;
  margin: 0.2em 0;
}
.ai-markdown hr {
  border: 0;
  border-top: 1px solid var(--color-border);
  margin: 0.4em 0;
}
.ai-markdown table {
  border-collapse: collapse;
  width: 100%;
  margin: 0.3em 0;
  font-size: 0.9em;
}
.ai-markdown th,
.ai-markdown td {
  border: 1px solid var(--color-border);
  padding: 3px 8px;
  text-align: left;
}
.ai-markdown thead tr {
  background: var(--color-code-bg);
}
.ai-markdown tbody tr:nth-child(even) {
  background: var(--color-stripe);
}
</style>
