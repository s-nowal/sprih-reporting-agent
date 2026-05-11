# PRD — Reporting PoC

# User Journey

## Onboarding
- Enterprise shares a Google Drive / OneDrive folder with our agent.

## Entry points
- Word plugin, or web agent interface.

## Auth
- Skipped in UI for now. Backend supports standard enterprise + user login.

## Chat
- Default view is a new chat window.
- First user message is used to generate the thread title (shown in the chat header and the conversation history).
- User can upload files into the thread; uploaded files can be deselected from the composer before sending so they aren't included as context.

## Sending a message
What happens server-side per user message — the unit an e2e test should drive.

1. **Thread bootstrap** (first message only): client calls `POST /threads`; backend inserts a `threads` row with empty `values` and scaffolds the thread workspace in S3.
2. **Run start**: client calls `POST /threads/{id}/runs/stream`; backend inserts a `jobs` row (`status=running`) and emits an SSE `metadata` event.
3. **Sync in** (if drive folder linked): user edits in drive are pulled into the thread workspace before the agent starts.
4. **Agent stream**: agent runs; each state update is emitted as an SSE `values` event with the serialized message list.
5. **State persist**: at end of stream, the final message list is written to `threads.values`.
6. **Sync out** (if drive folder linked): agent-written files are pushed back to drive; `thread_mirror_mappings.last_synced_at` is updated.
7. **Run end**: `jobs.status` set to `completed` (or `failed` on error); SSE `end` event closes the stream.
8. **Title** (first message only): the message is used to generate the thread title and persist it on `threads.title`. Visible immediately in the chat header and conversation history.

File uploads use a separate `POST /threads/{id}/files` and write bytes into the thread's S3 input area; the next run picks them up via the same input prefix the agent reads from.

## Plugin-only actions
- **Use selection as context**: the current Word selection appears as a chip in the composer and is sent with the next message; can be deselected like any other context item.
- **On assistant reply**: `Replace` (overwrite current selection), `Append` (insert after selection), `Copy`. Markdown is rendered to formatted Word content.
- **Sync on send**: toggle to upload the full document as markdown with the next message.
- **Pull into Word**: replace the document body with a synced file from the backend.

## Conversation history
- Sidebar lists prior threads.
- Each thread has an edit option:
  - Rename title.
  - Link to a drive folder by entering a folder name — the folder is created in drive. Once linked, the folder name is no longer editable from our UI.
  - Alternatively, link an existing folder by Google Drive / OneDrive folder ID.

## Drive sync (when a folder is linked)
The drive folder is the source of truth for user-editable files; the agent works against an internal copy and reconciles around each run.

- **Before a run** (sync in): user edits made directly in drive — adding, replacing, or removing files in the linked folder — are pulled in, so the agent sees the latest state when it starts.
- **During a run**: the user sees no live changes in drive; the agent operates on the snapshot it pulled.
- **After a run** (sync out): files the agent created or modified are written back to drive, preserving file IDs for files that already existed (so drive history stays intact).
- **Folder rename**: the user renames the linked folder in drive; on the next status fetch we read the live folder name from the provider and reflect it in the conversation history. If the folder is deleted or trashed, the link is shown as broken and the user can re-link.
- **What the user sees**: the file manager / chat UI reflects post-sync state. Between runs, the drive folder and the UI are consistent. Native Google Docs are not round-tripped and are skipped during sync.
- **Conflicts**: last writer wins per file, scoped to a single run boundary — concurrent edits to the same file by user and agent during a run are not merged.

# E2E Test Cases
One test case per journey step. Each case lists the request flow (router → handler → service → DB / external) so the test can assert state at every hop. Only TC1 is filled in for now; the rest are placeholders.

## TC1: New chat — first message (no drive folder)
Covers: thread bootstrap, run lifecycle, state persistence, title generation. Exercises the `Chat` and `Sending a message` sections of the journey.

**Preconditions**
- An `enterprises` row exists.
- No `threads` row for this user yet.
- No `mirror_credentials` row, or `parent_folder_id` is null.

**Flow**

| # | Client request | Server path | DB / storage writes |
|---|---|---|---|
| 1 | `POST /threads` `{}` | `routers/threads.py::create_thread` → `thread_handler.create_thread` → `services/agent/thread.py::create` | `INSERT threads(thread_id, enterprise_id, status='idle', metadata, values={}, interrupts={})`; S3 scaffolds `enterprise/{eid}/workspaces/{tid}/input/userUpload/.keep` and `output/.keep` |
| 2 | `POST /threads/{tid}/runs/stream` body `{assistant_id, input:{messages:[user_msg]}}` | `routers/runs.py::stream_run` → `run_handler.stream_run` | `INSERT jobs(id, enterprise_id, thread_id, job_type=assistant_id, status='running')`; SSE `metadata` event |
| 3 | (server-internal) | `mirror.get_provider` → no-op (no mapping) | none |
| 4 | (server-internal) | `agent_service.stream(...)` yields N states | SSE `values` events stream to client |
| 5 | (server-internal, stream end) | `services/agent/thread.py::update_values` | `UPDATE threads SET values={messages:[...]}, updated_at=now() WHERE thread_id=?` |
| 6 | (server-internal) | `mirror.sync_out` → no-op (no mapping) | none |
| 7 | (server-internal) | `job_service.update_status` | `UPDATE jobs SET status='completed' WHERE id=?`; SSE `end` |
| 8 | (server-internal, first-message side-effect — **new**) | title generator | `UPDATE threads SET title=<generated> WHERE thread_id=?` |
| 9 | `GET /threads/{tid}/state` | `routers/threads.py::get_state` → `services/agent/thread.py::get` | `SELECT * FROM threads WHERE thread_id=?` |

**Assertions**
- `threads` row exists with `title` set, `status='idle'`, and `values.messages` containing both `user_msg` and the agent reply (in order).
- Exactly one `jobs` row for this thread, `status='completed'`.
- No `thread_mirror_mappings` row exists.
- SSE event order: `metadata` → `values…` → `end` (no `error`).
- `GET /threads/{tid}/state` returns the same `values.messages` written in step 5.

## TC2: Continue conversation — Nth message
*TODO*

## TC3: Upload file to a thread
*TODO*

## TC4: Link thread to a brand-new drive folder
*TODO*

## TC5: Link thread to an existing drive folder by ID
*TODO*

## TC6: Folder renamed in drive — reflected in conversation history
*TODO*

## TC7: Drive sync_in — user edits a drive file, next run sees it
*TODO*

## TC8: Drive sync_out — agent writes a file, appears in drive after run
*TODO*

## TC9: Plugin — selection-as-context send + Replace assistant reply
*TODO*

## TC10: Conversation history — rename thread title
*TODO*

## TC11: Linked folder deleted in drive — link surfaced as broken, re-link works
*TODO*