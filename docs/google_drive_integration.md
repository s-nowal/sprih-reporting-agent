# Google Drive integration

The agent reads and writes files in S3 (the `LocalStorage` adapter for now).
This module mirrors a configurable subset of those files to a Google Drive
folder per thread, so the human user can sync the folder to their PC via
Drive Desktop and edit alongside the agent.

## Roles

| Role | Account (test) | Account (prod, future) |
|---|---|---|
| **Agent identity** — owns the OAuth refresh token, makes API calls | `sachchit.vekaria@sprih.com` | A single Sprih-owned Google account, e.g. `agent@sprih.com` |
| **Folder owner** — creates the parent `Sprih` folder, shares it with the agent | `write.to.sachchit@gmail.com` | The enterprise admin (data stays in the enterprise's Drive) |

Only the **agent identity** ever runs through OAuth. The folder owner just
shares a folder using the regular Drive UI — no app authorization on their
side. The same code path serves the test and the production model; only the
folder owner changes.

## Folder layout

```
Sprih/                          ← owned by folder owner; shared with agent
└── reporting-agent/            ← created lazily on first agent run
    └── {thread-title}/         ← random slug, e.g. plum-beacon-810
        ├── input/              ← mirrored ↔ S3
        └── output/             ← mirrored ↔ S3
        (workspace/, reference/ stay S3-only — see config.drive_mirror_subdirs)
```

Subfolder mirror policy is per-agent in `backend/config.py`:

```python
drive_mirror_subdirs: dict[str, list[str]] = {
    "reporting-agent": ["input", "output"],
}
```

## Sync model (lazy, turn-bounded)

```
agent run begins
    │
    ▼
drive_sync_service.setup_thread_folder(thread_id)   # creates Drive folders on first run
drive_sync_service.sync_in(thread_id)               # Drive → S3 for files modified since last sync
    │
    ▼
workspace_service.checkout(thread_id)               # S3 → temp workspace (existing)
agent runs (writes to temp workspace)
workspace_service.commit(thread_id)                 # temp → S3 (existing)
    │
    ▼
drive_sync_service.sync_out(thread_id)              # S3 → Drive for files modified since last sync
```

Hooked into `backend/handlers/run_handler.py:stream_run`. Failures in the
Drive layer are caught and logged — they never break the agent run.

**Conflict policy**: latest `modifiedTime` wins. Assumes the user and the
agent never edit a file simultaneously (they take turns).

## OAuth setup

### One-time GCP project setup

1. https://console.cloud.google.com → create project (e.g. `sprih-agent-drive`).
2. **APIs & Services → Library → Google Drive API → Enable**.
3. **OAuth consent screen** → User type **Internal** (Workspace).
   - Scopes: `https://www.googleapis.com/auth/drive`.
4. **Credentials → Create OAuth client ID → Web application**.
   - Authorized redirect URI: `http://localhost:8000/auth/google/callback`
     (add prod URLs when deploying).
5. Copy the client id and secret into `.env`:
   ```
   SPRIH_GOOGLE_OAUTH_CLIENT_ID=<id>
   SPRIH_GOOGLE_OAUTH_CLIENT_SECRET=<secret>
   SPRIH_AUTH_DEV_MODE=true
   ```

### Per-enterprise bootstrap

Each enterprise needs (in order):

1. **OAuth grant from the agent identity.** Hit `/auth/google/start` and
   open the returned URL in a browser signed in as the agent account. Grant
   Drive access. Browser redirects to `/callback` and the refresh token is
   stored in `google_credentials`.
2. **Folder share from the folder owner.** The owner creates a folder named
   `Sprih` in their Drive and shares it with the agent identity as **Editor**.
3. **Register the folder ID.** `POST /auth/google/parent-folder` with the
   folder ID. The handler verifies the agent can list the folder before
   persisting (proves the share is correct).

## Worked example (the test setup we used)

Agent identity: `sachchit.vekaria@sprih.com`. Folder owner: `write.to.sachchit@gmail.com`. Test folder ID: `1RcgD8HzYs0H-q-EKIo1tnXJX2vyRwYNP`.

```bash
# 1. Get the consent URL
curl -s http://localhost:8000/auth/google/start
# {"authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?...", "enterprise_id": "sprih"}

# 2. Open the authorize_url in a browser logged in as sachchit.vekaria@sprih.com.
#    Click Allow on the consent screen. Browser lands on /callback and shows
#    "Connected ✓" — refresh token now persisted for enterprise=sprih.

# 3. Verify
curl -s http://localhost:8000/auth/google/status
# {"connected": true, "agent_email": "sachchit.vekaria@sprih.com",
#  "drive_parent_folder_id": null}

# 4. As write.to.sachchit@gmail.com (in browser):
#    - Drive → New Folder → "Sprih"
#    - Right-click → Share → add sachchit.vekaria@sprih.com as Editor
#    - Copy the folder ID from the URL (the path component after /folders/)

# 5. Tell the backend which folder is the parent
curl -X POST http://localhost:8000/auth/google/parent-folder \
  -H "Content-Type: application/json" \
  -d '{"drive_parent_folder_id": "1RcgD8HzYs0H-q-EKIo1tnXJX2vyRwYNP"}'
# {"connected": true, "agent_email": "sachchit.vekaria@sprih.com",
#  "drive_parent_folder_id": "1RcgD8HzYs0H-q-EKIo1tnXJX2vyRwYNP"}
```

After this, the next reporting-agent run on a thread automatically:
- creates `Sprih/reporting-agent/{random-title}/input/` and `output/`
- pulls anything from those folders into S3 before the agent reads
- pushes anything the agent writes back to Drive after the run commits

## Endpoints reference

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/auth/google/start`         | Returns the Google consent URL for the calling enterprise. |
| `GET`  | `/auth/google/callback`      | Google redirects here with the auth code; refresh token gets persisted. |
| `GET`  | `/auth/google/status`        | Returns `{connected, agent_email, drive_parent_folder_id}`. |
| `POST` | `/auth/google/parent-folder` | Persists the shared `Sprih` folder ID after verifying access. |

## Components

| File | Responsibility |
|---|---|
| `backend/infra/google_drive.py` | `GoogleDriveClient` — thin Drive v3 wrapper (folder/file CRUD, list, download, upload). Pure I/O. |
| `backend/services/drive_sync_service.py` | `setup_thread_folder`, `sync_in`, `sync_out`, credential persistence helpers, random title generator. |
| `backend/routers/google_auth.py` | OAuth flow + folder registration endpoints. |
| `backend/models/enterprise.py` | Tenant row (default `sprih` seeded at startup). |
| `backend/models/google_credentials.py` | Refresh token + parent folder ID per enterprise. |
| `backend/models/thread_drive_mapping.py` | Per-thread Drive folder ID + `last_synced_at`. |
| `backend/handlers/run_handler.py` | Calls `setup_thread_folder` + `sync_in` before checkout, `sync_out` after commit. |

## Limitations (v1 — out of scope)

- **Native Google Docs**: skipped on sync (logged) — only binary formats
  (`.docx`, `.xlsx`, `.pdf`, `.txt`, `.md`) round-trip cleanly.
- **Renames / deletions in Drive**: ignored. The S3 copy keeps the old
  name / content until next agent write.
- **Concurrent edits**: relies on the user/agent never editing the same
  file at the same time. Conflicts resolve by `modifiedTime` last-write-wins.
- **Push notifications**: not used. Sync runs only at agent-turn boundaries
  (≈ on the next user message). For shorter latency, add a Drive
  `changes.watch` webhook later.
- **Granular permissions**: anything inside the shared `Sprih` folder is
  visible to the folder owner — no per-thread ACLs.
