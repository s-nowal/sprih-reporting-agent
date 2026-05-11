# ConOps — Reporting PoC

This document is a single spec laid out in four sections.

1. **User Journey** — one continuous scenario, told through a concrete persona, covering every product flow including the back-and-forth between our chat and Google Drive.
2. **Per-Step Backend Writes** — for each backend-touching step in the journey, the API endpoint(s) called and the writes that follow across the database, S3, and Drive.
3. **Database Tables (Schema and Examples)** — every table referenced from section 2, with example rows tied to the section 1 scenario so the column shapes are concrete.
4. **Storage Layout — S3 and Drive (with Examples)** — the S3 namespace per thread and the linked Drive folder, with example file trees so the sync directions in section 2 are concrete.

The doc has two readers. **Humans** read straight through and look for places where the user does something but no row, no S3 path, and no Drive write records it — those are gaps. **Testing agents** treat each `[§2.X]` step as one test case: drive the listed endpoints in order with the listed bodies, then assert the listed writes against DB, S3, and Drive. Steps marked `[FE-only]` are purely client-side; their backend linkage will be added in a later pass.

---

## 1. User Journey

Sara Chen is an ESG analyst at Acme Corp. Acme's admin has already shared a single root folder in Google Drive with our agent during onboarding — that's all that's needed before any analyst at Acme can start using the product. End-user authentication is skipped in the UI for the PoC, so Sara lands directly into the product without a sign-in screen.

Sara opens Word `[FE-only]`. She clicks into our plugin from the Word ribbon, and the plugin pane opens beside her empty document `[FE-only]`. (She could instead open the web agent interface in a browser; both clients give the same chat experience, with the plugin layering document-aware actions on top.) The default new-chat view greets her: an empty thread, no title, no messages, just the composer `[FE-only]`.

Sara has been asked to draft Acme's Q3 2025 sustainability report and decides to start with the hardest part. She types her first message — *"Help me draft the Scope 3 emissions section for Acme's Q3 2025 sustainability report. Focus on supplier data and the GHG Protocol categories that matter most for a mid-size manufacturer."* — and sends. The composer locks while the agent works `[FE-only]`, the reply streams into the chat as the agent walks through the relevant Scope 3 categories, and once the run finishes a generated title — *"Q3 2025 Scope 3 emissions draft"* — appears in the chat header and in the conversation history sidebar. **[§2.1]**

She reads the reply, gets pulled into a meeting, and clicks `+` to clear the composer for later `[FE-only]`. When she comes back later that afternoon, she opens the conversation history sidebar to pick up where she left off; the sidebar fetches her thread list and *"Q3 2025 Scope 3 emissions draft"* sits near the top. **[§2.2]** She clicks it; the conversation reloads exactly as it was at the end of the last run, with the title in the header and the message exchange restored in the chat. **[§2.3]**

She types a follow-up: *"For Category 1 (Purchased goods and services), what supplier data should we be requesting from procurement?"* The reply streams in just like the first one did, extending the conversation in place. **[§2.4]**

A few turns in, Sara wants the agent's advice grounded in Acme's actual supplier data. She drags `acme_top50_suppliers_q3.csv` into the composer; the chip appears and the file uploads to the thread immediately. **[§2.5]** The composer lets her pull the chip off before sending if she changes her mind `[FE-only]`. She keeps it, types *"Use this supplier list to identify the top emission contributors and suggest the data we should collect from each,"* and sends. The agent reads the CSV from the thread and the reply names specific suppliers. **[§2.4]**

By now Sara is producing real outputs and wants them to live somewhere her team can collaborate on. She opens the conversation history sidebar **[§2.2]**, finds this thread, and clicks edit `[FE-only]`. She types a folder name — *"Q3 2025 ESG Report"* — and saves. The folder is created in Acme's Google Drive (under the root the admin shared at onboarding) and the thread is now mirrored to it. **[§2.6]**

Around the same time, Sara has a separate CSRD-disclosures thread she's been working on with her team for weeks. Her team already maintains a Drive folder for that effort — *"CSRD 2024 disclosures"* — full of supporting documents and prior drafts. She opens that thread's edit panel, copies the folder's ID out of the Drive URL in her browser, and pastes it in. The thread is attached to the existing folder; Drive isn't asked to create anything new. **[§2.7]**

Back on the Q3 thread, she opens her Google Drive in the browser and drops two reference PDFs directly into the new *Q3 2025 ESG Report* folder — `ghg_protocol_scope3_guidance.pdf` and `acme_q3_2024_sustainability_report.pdf`. She comes back to the chat and asks the agent to factor them in. On her next message, the agent's pre-run sync pulls those PDFs into the thread, and the reply now cites them. **[§2.8]**

Over the next several turns, the agent drafts Sara's report section by section, writing each draft as a markdown file into the linked Drive folder — `scope1_emissions.md`, `scope2_emissions.md`, `scope3_methodology.md`, `data_gaps.md`. After each run completes, Sara refreshes Drive in the browser and finds the new files there, ready to review. **[§2.8]**

She opens `scope3_methodology.md` directly in Drive and rewrites a paragraph that doesn't match Acme's actual supplier engagement process. She saves the file in Drive (it stays as the same Drive file with the same file id; only its contents change) and comes back to the chat. The next time she sends a message, the agent picks up her edited version of the file rather than its own previous version, and continues from there. **[§2.8]**

Sara's colleague Priya, who has access to the same Drive folder, drops `supplier_emissions_q3.csv` into the folder while Sara is in the middle of the chat. Sara hasn't refreshed Drive yet, but on her next message that file is already in scope for the agent — sync-in pulls in everything new since the last run. **[§2.8]**

A few days in, Sara renames the linked folder in Drive — from *"Q3 2025 ESG Report"* to *"Q3 2025 ESG Report (FINAL)"* — to mark it as ready for review. She comes back to the chat. The next time the conversation history sidebar refreshes **[§2.2]**, the response shaping reads the live folder name from Drive, notices it has drifted from the stored value, and updates it; the new name appears in the sidebar without any action from Sara. **[§2.9]**

Sara is now in Word reviewing the consolidated draft her team has assembled. She highlights a paragraph in the *Scope 3 — Category 4 (Upstream transportation)* section `[FE-only]` and a chip with that selection appears in the composer `[FE-only]`. She sends *"Tighten this paragraph to focus on the modal split — air vs ocean vs road — and cite Acme's actual lanes."* **[§2.10]** The agent replies with a tighter version. She clicks `Replace` and the paragraph in the document is updated in place; she could have used `Append` to insert the reply after the selection or `Copy` to grab it for the clipboard `[FE-only]`.

For her next question she flips on **Sync on send** so the agent can reason over the whole document, not just a selection — the toggle itself is `[FE-only]`; on send the document content rides as part of the run request, covered by **[§2.4]**. Later, after the agent has written an updated `consolidated_draft.docx` into the linked Drive folder, she clicks **Pull into Word** to bring that file into her Word document as the working copy. **[§2.13]**

Going back to the sidebar **[§2.2]**, Sara notices the auto-generated title is fine but not as descriptive as she wants for a report she'll come back to over weeks. She clicks rename and changes it to *"Q3 2025 sustainability report — full draft"*. The title updates in both the chat header and the sidebar. **[§2.11]**

A few days later, Priya accidentally moves the *Q3 2025 ESG Report (FINAL)* folder to Drive's trash while reorganizing her own files. Sara opens her sidebar **[§2.2]** and clicks back into the Q3 thread **[§2.3]**; the live read against Drive fails for the linked folder and the UI surfaces the link as broken. She clicks edit and re-links to a freshly-created folder named *"Q3 2025 ESG Report — recovered"*; sync resumes from there. **[§2.12]**

---

## 2. Per-Step Backend Writes

Each subsection corresponds to a `[§2.X]` marker in section 1. Every entry lists the API endpoint(s), request body shape, and the writes that follow against the database, S3, and Drive. Reads are listed where they shape what the user sees next.

Authentication context: every request resolves to an `(enterprise_id, user_id)` pair via the auth dependency. These are not in the request body — the writes use whatever the auth context resolves to.

### 2.1 First message on a fresh thread

**Trigger:** Sara types her first message and sends.

**API calls (in order):**

1. `POST /threads`  
   Body: `{}`  
   Response: `{thread_id, enterprise_id, user_id, status, created_at, updated_at}`
2. `POST /threads/{thread_id}/runs/stream`  
   Body: `{assistant_id: "<id>", input: {messages: [{role: "user", content: "<first message>"}]}}`  
   Response: SSE stream — `metadata` event, then `values` events, then `end` (or `error`).

**Writes:**

On `POST /threads`:
- `threads` — INSERT: `thread_id` (uuid), `enterprise_id`, `user_id`, `title=NULL`, `status='idle'`, `created_at=now()`, `updated_at=now()`.
- S3 — scaffold `enterprise/{enterprise_id}/workspaces/{thread_id}/input/userUpload/.keep` and `enterprise/{enterprise_id}/workspaces/{thread_id}/output/.keep`.

On `POST /threads/{thread_id}/runs/stream` (run start):
- `jobs` — INSERT: `id` (uuid), `enterprise_id`, `thread_id`, `job_type='<assistant_id>'`, `status='running'`, `created_at=now()`.
- `threads` — UPDATE: `status: 'idle' → 'busy'`, `updated_at=now()`.

During stream (per agent node-step):
- LangGraph checkpointer — APPEND a checkpoint row carrying the current `values` (messages list, etc.) for this `thread_id`.

On stream end (success):
- `jobs` — UPDATE: `status: 'running' → 'completed'`, `updated_at=now()`.
- `threads` — UPDATE: `status: 'busy' → 'idle'`, `title=<generated from first user message>` (first-message-only side-effect), `updated_at=now()`.

On stream end (failure):
- `jobs` — UPDATE: `status='failed'`, `updated_at=now()`.
- `threads` — UPDATE: `status='error'`, `updated_at=now()`.

### 2.2 Open conversation history sidebar

**Trigger:** Sara opens the sidebar.

**API call:**
- `GET /threads`  
  Response: `[{thread_id, title, status, updated_at, mirror: {folder_name, status} | null}, ...]`

**Effect:** returns the user's threads. For threads with a `thread_mirror_mappings` row, the response includes the live folder name read from the provider — see §2.9 for the write that follows when Drive's name has drifted from the stored value.

### 2.3 Open a prior thread

**Trigger:** Sara clicks a thread in the sidebar.

**API call:**
- `GET /threads/{thread_id}/state`  
  Response: `{values: {messages: [...]}, status, ...}`

**Effect:** returns the latest checkpoint from the LangGraph checkpointer for this thread.

### 2.4 Send a follow-up message on an existing thread

**Trigger:** Sara types a follow-up and sends. Also covers the send-with-uploaded-file case (the upload itself is §2.5; the run that follows lands here).

**API call:**
- `POST /threads/{thread_id}/runs/stream`  
  Body: `{assistant_id: "<id>", input: {messages: [{role: "user", content: "<follow-up>"}]}}`  
  Response: SSE stream — `metadata`, `values`..., `end` (or `error`).

**Writes:**

On run start:
- `jobs` — INSERT: `id`, `enterprise_id`, `thread_id`, `job_type`, `status='running'`, `created_at=now()`.
- `threads` — UPDATE: `status: 'idle' → 'busy'`, `updated_at=now()`.

During stream (per node-step):
- LangGraph checkpointer — APPEND a checkpoint row extending the thread's checkpoint chain.

On stream end:
- `jobs` — UPDATE: `status` to `'completed'` or `'failed'`, `updated_at=now()`.
- `threads` — UPDATE: `status` to `'idle'` or `'error'`, `updated_at=now()`. (Title remains as set in §2.1.)

### 2.5 Upload a file to the thread

**Trigger:** Sara drags a file into the composer.

**API call:**
- `POST /threads/{thread_id}/files`  
  Body: multipart/form-data with the file bytes  
  Response: `{file_id, filename, size, uploaded_at}`

**Writes:**
- S3 — write the file bytes at `enterprise/{enterprise_id}/workspaces/{thread_id}/input/userUpload/{filename}`. The next run reads from this prefix.

### 2.6 Link thread to a brand-new Drive folder by name

**Trigger:** in the edit-thread panel, Sara types a folder name and saves.

**API call:**
- `POST /threads/{thread_id}/mirror`  
  Body: `{provider: "google_drive" | "onedrive", folder_name: "<name>"}`  
  Response: `{thread_id, provider, folder_id, folder_name, status, last_synced_at}`

**Writes:**
- Drive (external) — create a new folder under `mirror_credentials.parent_folder_id`; the response carries the new folder id.
- `thread_mirror_mappings` — INSERT: `thread_id`, `provider`, `folder_id` (returned from Drive), `folder_name`, `status='active'`, `last_synced_at=NULL`, `created_at=now()`, `updated_at=now()`.

### 2.7 Link thread to an existing Drive folder by ID

**Trigger:** in the edit-thread panel, Sara pastes a folder id and saves.

**API call:**
- `POST /threads/{thread_id}/mirror`  
  Body: `{provider: "google_drive" | "onedrive", folder_id: "<id>"}`  
  Response: `{thread_id, provider, folder_id, folder_name, status, last_synced_at}`

**Writes:**
- Drive (external) — read the folder name for the given id (verifies the folder exists and is accessible).
- `thread_mirror_mappings` — INSERT: `thread_id`, `provider`, `folder_id`, `folder_name` (from the live read), `status='active'`, `last_synced_at=NULL`, `created_at=now()`, `updated_at=now()`.

### 2.8 Run on a thread that has a `thread_mirror_mappings` row

**Trigger:** Sara sends a message on a mirrored thread. Covers all the Drive back-and-forth in section 1: PDFs Sara dropped into Drive, files Priya added, files Sara edited in Drive, files the agent wrote into Drive.

**API call:** same as §2.4 — `POST /threads/{thread_id}/runs/stream`.

**Writes:** all writes from §2.4, plus:

On run start (sync-in, before the agent starts):
- Drive (external, read) — list the linked folder's contents and download every file that has changed since `last_synced_at`. Native Google Docs (Doc, Sheet, Slide MIME types) are filtered out.
- S3 — write the downloaded contents into `enterprise/{enterprise_id}/workspaces/{thread_id}/input/` (mirroring the Drive folder's current state). Files removed from Drive since the last sync are removed from this prefix as well.

During the run:
- S3 — the agent writes its output files into `enterprise/{enterprise_id}/workspaces/{thread_id}/output/`.

On stream end (sync-out, success path):
- Drive (external, write) — for each file under `output/`: if a file with the same name already exists in the linked folder, update its contents in place (preserving the Drive file id and version history); otherwise create a new file in the linked folder and capture the new file id.
- `thread_mirror_mappings` — UPDATE: `last_synced_at=now()`, `updated_at=now()`.

Within a single run, the most recent writer to a given filename wins at the run boundary (last-writer-wins per file).

### 2.9 Linked folder renamed in Drive — UI reflects the new name

**Trigger:** Sara has renamed the folder in Drive directly. Surfaced on the next sidebar refresh or thread fetch.

**API call:**
- `GET /threads` (sidebar refresh) or `GET /threads/{thread_id}` (when she lands directly on the thread). The response shaping reads the live folder name from the provider for any thread with a mirror row.

**Writes:**
- `thread_mirror_mappings` — UPDATE: `folder_name=<live name from provider>` (only when it differs from the stored value), `updated_at=now()`.

### 2.10 Plugin: send selection as context

**Trigger:** Sara highlights text in Word and sends a message with the selection chip in the composer.

**API call:**
- `POST /threads/{thread_id}/runs/stream`  
  Body: `{assistant_id, input: {messages: [{role: "user", content: "<message>", context: [{type: "selection", text: "<selected text>"}]}]}}`

**Writes:** identical to §2.4 (the selection is carried inside the run input message and persists into the LangGraph checkpoint chain like any other user message content). The reply actions `Replace`, `Append`, `Copy` are local Word edits.

### 2.11 Rename a thread title from the sidebar

**Trigger:** Sara clicks rename on a thread in the sidebar, edits the title, saves.

**API call:**
- `PATCH /threads/{thread_id}`  
  Body: `{title: "<new title>"}`  
  Response: `{thread_id, title, ...}`

**Writes:**
- `threads` — UPDATE: `title=<new title>`, `updated_at=now()`.

### 2.12 Linked folder deleted in Drive, then re-linked

**Trigger (broken-link surface):** Sara opens the sidebar or a mirrored thread; the live read against the provider reports the linked folder as missing or trashed.

**API call (detect):**
- `GET /threads` or `GET /threads/{thread_id}` — same calls as §2.9, but the live read fails for the folder.

**Writes (detect):**
- `thread_mirror_mappings` — UPDATE: `status: 'active' → 'broken'`, `updated_at=now()`.

**Trigger (re-link):** in the edit-thread panel, Sara provides a different folder name or id.

**API call (re-link):**
- `POST /threads/{thread_id}/mirror` — same body shape as §2.6 (by name) or §2.7 (by id).

**Writes (re-link):**
- Drive (external) — same as §2.6 / §2.7 depending on whether a new folder is created or an existing one is attached.
- `thread_mirror_mappings` — UPSERT for this `thread_id`: `provider`, `folder_id`, `folder_name`, `status='active'`, `last_synced_at=NULL`, `updated_at=now()`. (The next run on this thread takes the §2.8 path and updates `last_synced_at`.)

### 2.13 Plugin: Pull into Word

**Trigger:** Sara clicks "Pull into Word" against a synced file the agent has produced.

**API call:**
- `GET /threads/{thread_id}/files/{file_id}`  
  Response: file bytes (the plugin renders them into the Word document).

**Effect:** returns file bytes from S3 (`enterprise/{enterprise_id}/workspaces/{thread_id}/output/{filename}`).

---

## 3. Database Tables (Schema and Examples)

Each table referenced in section 2, with one or two example rows tied to Sara's scenario. Timestamps are shown human-readable; in practice they are stored as UTC.

### `enterprises`
One row per onboarded enterprise. Every other row scopes back to one of these.

| id              | name      | created_at          |
|-----------------|-----------|---------------------|
| ent_acme        | Acme Corp | 2026-01-15 09:32:04 |

### `users`
One row per end user. Resolved from the auth context on every request.

| id            | enterprise_id | email                | name        | created_at          |
|---------------|---------------|----------------------|-------------|---------------------|
| usr_sara      | ent_acme      | sara.chen@acme.com   | Sara Chen   | 2026-01-15 09:33:12 |
| usr_priya     | ent_acme      | priya.r@acme.com     | Priya R     | 2026-01-15 09:33:48 |

### `threads`
One row per chat thread. Holds the thread's metadata and current run-status. The conversation content itself lives in the LangGraph checkpointer, not here.

| thread_id    | enterprise_id | user_id   | title                                          | status | created_at          | updated_at          |
|--------------|---------------|-----------|------------------------------------------------|--------|---------------------|---------------------|
| thr_q3_2025  | ent_acme      | usr_sara  | Q3 2025 sustainability report — full draft     | idle   | 2026-04-12 10:15:00 | 2026-04-22 16:08:42 |
| thr_csrd_24  | ent_acme      | usr_sara  | NULL                                           | busy   | 2026-04-22 17:00:00 | 2026-04-22 17:00:01 |

`status`: `idle`, `busy`, `interrupted`, `error`. `title` is `NULL` until the first message generates one (§2.1) and may later be edited via §2.11.

### `jobs`
One row per run. Every `POST /runs/stream` creates one row, finalized at end of stream.

| id             | enterprise_id | thread_id    | job_type        | status     | created_at          | updated_at          |
|----------------|---------------|--------------|-----------------|------------|---------------------|---------------------|
| job_q3_2025_r1 | ent_acme      | thr_q3_2025  | research_agent  | completed  | 2026-04-12 10:15:01 | 2026-04-12 10:18:42 |
| job_csrd_r1    | ent_acme      | thr_csrd_24  | research_agent  | running    | 2026-04-22 17:00:01 | 2026-04-22 17:00:01 |

`status`: `running`, `completed`, `failed`, `interrupted`.

### LangGraph checkpointer (MariaDB)
Internal tables managed by LangGraph. One checkpoint is appended per agent node-step. `GET /threads/{thread_id}/state` reads the latest checkpoint. We don't write to these directly — the agent runtime does.

Conceptual example (one row per checkpoint):

| thread_id    | checkpoint_id   | parent_checkpoint_id | values (json)                                                                                                | created_at              |
|--------------|-----------------|----------------------|--------------------------------------------------------------------------------------------------------------|-------------------------|
| thr_q3_2025  | ckpt_q3_2025_03 | ckpt_q3_2025_02      | {"messages":[{"role":"user","content":"Help me draft..."},{"role":"assistant","content":"Scope 3..."}]}      | 2026-04-12 10:18:42.301 |

### `thread_mirror_mappings`
One row per Drive-linked thread. Created on §2.6 / §2.7, updated on §2.8 / §2.9, flipped to `broken` on §2.12.

| thread_id    | provider     | folder_id   | folder_name                          | status  | last_synced_at      | created_at          | updated_at          |
|--------------|--------------|-------------|--------------------------------------|---------|---------------------|---------------------|---------------------|
| thr_q3_2025  | google_drive | drv_q3rep   | Q3 2025 ESG Report — recovered       | active  | 2026-04-22 16:08:42 | 2026-04-21 11:00:00 | 2026-04-22 16:08:42 |
| thr_csrd_24  | google_drive | drv_csrd24  | CSRD 2024 disclosures (FINAL)        | broken  | 2026-04-09 16:30:00 | 2026-03-30 11:00:00 | 2026-04-22 14:55:00 |

`status`: `active`, `broken`. `last_synced_at` is `NULL` until the first sync-out completes (§2.8 success path).

### `mirror_credentials`
Provider credentials and the admin-shared parent folder, scoped to the enterprise. New folders created via "link by name" (§2.6) land underneath `parent_folder_id`.

| enterprise_id | provider     | refresh_token (encrypted) | parent_folder_id | created_at          | updated_at          |
|---------------|--------------|---------------------------|------------------|---------------------|---------------------|
| ent_acme      | google_drive | <enc>                     | drv_acme_root    | 2026-01-15 09:35:00 | 2026-01-15 09:35:00 |

---

## 4. Storage Layout — S3 and Drive (with Examples)

This section describes the two non-database stores referenced in section 2: the S3 thread workspace and the linked Drive folder. Example trees use Sara's `thr_q3_2025` thread.

### 4.1 S3 thread workspace
Per-thread namespace, scaffolded on thread creation (§2.1). Owned by us and not directly visible to the user.

```
enterprise/ent_acme/workspaces/thr_q3_2025/
  input/
    userUpload/
      .keep
      acme_top50_suppliers_q3.csv             ← user upload via §2.5
      ghg_protocol_scope3_guidance.pdf        ← pulled from Drive by §2.8 sync-in
      acme_q3_2024_sustainability_report.pdf  ← pulled from Drive by §2.8 sync-in
      supplier_emissions_q3.csv               ← pulled from Drive by §2.8 sync-in (added by Priya)
  output/
    .keep
    scope1_emissions.md                       ← agent-written; §2.8 sync-out pushes to Drive
    scope2_emissions.md                       ← agent-written; §2.8 sync-out pushes to Drive
    scope3_methodology.md                     ← agent-written; §2.8 sync-out pushes to Drive
    data_gaps.md                              ← agent-written; §2.8 sync-out pushes to Drive
    consolidated_draft.docx                   ← agent-written; fetched by Pull into Word (§2.13)
```

Notes:
- `input/userUpload/` holds user uploads from §2.5 and Drive sync-in pulls from §2.8.
- `output/` holds agent-written files. §2.8 sync-out pushes everything from here to the linked Drive folder. §2.13 reads from here.

### 4.2 Linked Drive folder
The user-facing source of truth for files when a thread is mirrored. Owned by Drive and edited by users directly.

```
drv_acme_root/                                       ← admin-shared root (mirror_credentials.parent_folder_id)
  Q3 2025 ESG Report — recovered/                    ← linked to thr_q3_2025 (folder_id: drv_q3rep)
    ghg_protocol_scope3_guidance.pdf                 ← Sara dropped in via Drive UI; §2.8 sync-in source
    acme_q3_2024_sustainability_report.pdf           ← Sara dropped in via Drive UI; §2.8 sync-in source
    supplier_emissions_q3.csv                        ← Priya dropped in via Drive UI; §2.8 sync-in source
    scope1_emissions.md                              ← agent-written via §2.8 sync-out
    scope2_emissions.md                              ← agent-written via §2.8 sync-out
    scope3_methodology.md                            ← agent-written via §2.8 sync-out, then edited by Sara in Drive
    data_gaps.md                                     ← agent-written via §2.8 sync-out
    consolidated_draft.docx                          ← agent-written via §2.8 sync-out
```

### 4.3 Sync semantics

Per run on a mirrored thread (§2.8):

- **Sync-in (Drive → S3):** the linked folder is listed and every file is downloaded into `input/` of the S3 workspace, except native Google Docs (Doc / Sheet / Slide MIME types) which are filtered out. Files removed from Drive since the previous sync are removed from `input/` to match.
- **Agent run:** the agent reads from `input/`, writes to `output/`. Drive is not touched mid-run.
- **Sync-out (S3 `output/` → Drive):** every file under `output/` is pushed to the linked folder. If a file with the same name already exists in Drive, its contents are updated in place, preserving the Drive file id and version history. Otherwise a new Drive file is created.
- **Conflict resolution:** within a single run, last writer wins per filename at the run boundary.
