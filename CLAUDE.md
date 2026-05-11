# ESG Reporting Platform

## Project
FastAPI backend + Word add-in frontend for AI-powered ESG (Environmental, Social, Governance) compliance reporting. Agents are built with LangGraph (MIT) and exposed via an Agent Protocol-compatible API.

## Stack
- **Runtime**: Python 3.12+, managed with `uv`
- **Backend**: FastAPI + uvicorn
- **Agent framework**: LangGraph (MIT) — swap boundary is `AgentService`
- **LLM**: Anthropic Claude — `claude-sonnet-4-6` for the agents, `claude-haiku-4-5` for fast helpers (e.g. first-message title generator)
- **Frontend**: Vue 3 + Vite Word task-pane add-in at `word-plugin/` (Office.js)
- **Databases**: MariaDB (metadata), Neo4j (knowledge graph), Qdrant (vector search)

## Commands
```bash
./start-server.sh                   # start backend (:8003) + word-plugin (:3000, HTTPS)
./stop-server.sh                    # stop both
uv run uvicorn backend.main:app --reload --port 8003   # backend only
uv run pytest                       # run tests
uv add <package>                    # add dependency
docker compose up -d                # start MariaDB, Neo4j, Qdrant
```

## Environment
Copy `.env.example` to `.env` and fill in:
- `ANTHROPIC_API_KEY`
- `SPRIH_JWT_SECRET` (any string for dev)
- `SPRIH_AUTH_DEV_MODE=true` (skip JWT auth in dev)

## Backend structure
```
backend/
  main.py                       # FastAPI app, CORS, router registration
  config.py                     # Settings (env prefix: SPRIH_)
  security/auth.py              # JWT decode → EnterpriseContext dependency
  routers/                      # HTTP layer (validation + auth only)
    threads.py                  # /threads CRUD (Agent Protocol)
    runs.py                     # /threads/{tid}/runs/stream (SSE)
    files.py                    # /threads/{tid}/files multipart upload + CRUD
    mirror.py                   # /threads/{tid}/mirror — Drive link / unlink
    sources.py                  # /sources business endpoint
    google_auth.py              # OAuth callback for Drive integration
  schemas/                      # Pydantic models, one file per router
  handlers/                     # Orchestration (calls services, raises HTTP)
    thread_handler.py
    run_handler.py
    file_handler.py
    mirror_handler.py
    source_handler.py
  services/
    agent/                      # Agent execution + thread persistence (SWAP POINT)
      base.py                   # Abstract AgentService interface
      langgraph_service.py      # LangGraph implementation + singleton
      thread.py                 # threads table CRUD + status flips
      title.py                  # First-message title generator (Haiku)
      workspace.py              # S3 workspace prefix resolution
    mirror/                     # Drive sync orchestration
      base.py                   # MirrorProvider base + setup_thread_folder, sync_in/out
      google_drive.py           # GoogleDriveMirrorProvider
      credentials.py            # mirror_credentials CRUD
    job.py                      # jobs table CRUD (run lifecycle)
    ingestion/                  # Ingestion pipeline (sources → vectors)
    embedding/                  # Embedding helpers
    extraction/                 # Source extraction
    file_policy.py              # Read/write policy for thread workspaces
  models/                       # SQLAlchemy ORM (threads, jobs, mirror_*, enterprise, …)
  infra/
    db.py                       # Async SQLAlchemy engine + session factory
    registry.py                 # Module-level singletons (storage, session_factory)
    storage.py                  # LocalStorage (S3 adapter for sandbox)
    google_drive.py             # GoogleDriveClient (googleapiclient wrapper)
  ai/
    agents/
      reporting_agent.py        # Default assistant_id="reporting-agent"
      research_agent.py         # Researcher subagent (web_search + web_crawl)
    tools/                      # Agent-callable tools
    prompts/                    # System prompts by consumer type
```

## Architecture rules

### Routers (`routers/`)
- Named after the endpoint they serve (`sources.py` → `/sources`, `artifacts.py` → `/artifacts`)
- Responsibility: Pydantic schema validation + auth injection only
- No business logic, no direct DB/service calls
- Every router has a corresponding schema file with the same name

### Schemas (`schemas/`)
- One file per router, named identically (`routers/sources.py` ↔ `schemas/sources.py`)
- Define all request and response models for that router

### Handlers (`handlers/`)
- Orchestrate the response: call one or more services, combine results, raise HTTP errors
- Know about the HTTP context (enterprise, request params) but not FastAPI internals
- Single handler per router domain

### Services (`services/`)
- Isolated business logic: DB queries, S3 operations, agent execution
- No knowledge of HTTP, enterprise context, or request shape
- Accept plain primitives/dicts, return plain primitives/dicts
- The swap point for replacing infrastructure (e.g. `AgentService` swaps the LangGraph graph)

### Flow
```
Router (validate + auth) → Handler (orchestrate) → Service (execute)
```

## Agent Protocol
The threads/runs/assistants API follows the LangGraph Platform API spec. Any client using `@langchain/langgraph-sdk` works against it. Custom business endpoints (`/sources`, `/files`, `/mirror`) are separate.

## Design source

The reporting product's behavior is specified in `docs/ConOps.md`. One continuous user journey with `[§2.X]` anchors links each user action to its per-step backend writes (API + DB + S3 + Drive), with example rows for every backend table and storage layout. When changing product behavior, update the ConOps first — the e2e suite under `tests/e2e/test_conops_2_*.py` reads as the spec made executable.

## Tests

End-to-end tests live in `tests/e2e/` and map one-to-one to ConOps subsections (e.g. `test_conops_2_1_first_message.py` covers ConOps §2.1). Each test drives the documented API sequence and asserts against the real MariaDB / S3 / Drive stack — no agent mocking. Journey state is encoded in composable fixtures in `tests/e2e/conftest.py`:

- `fresh_thread` — just past `POST /threads`
- `thread_with_history` — after one completed run (post-§2.1 state)
- `real_mirror_credentials` — test enterprise has Drive linkage (copies sprih's google_drive credentials)
- `drive_cleanup` — trashes created Drive folders + clears mapping rows on teardown

Run: `uv run pytest tests/e2e/` (requires Docker stack + `.env` with `ANTHROPIC_API_KEY`).

Cross-loop note: DB fixtures use sync `pymysql` for setup/teardown to avoid `pytest-asyncio` finalising `AsyncSession` in a different event loop than the one that opened the pool.

## Documentation standard

### Docstrings
Every module, class, and public function **must** have a docstring that includes:
- **Summary**: one-line description of what it does (logic, not just the name restated)
- **Args**: each parameter with type and meaning
- **Returns**: what is returned and its structure
- **Raises**: any exceptions the caller should expect

Use Google-style docstrings. Keep them factual — describe logic, not aspirations.

### Inline comments
Add comments at major flow steps so a reader can follow the function's logic without reading every line. Use `# --- Section name ---` separators for distinct phases within long functions.
