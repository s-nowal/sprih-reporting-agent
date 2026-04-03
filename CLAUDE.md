# ESG Reporting Platform

## Project
FastAPI backend + Next.js frontend for AI-powered ESG (Environmental, Social, Governance) compliance reporting. Agents are built with LangGraph (MIT) and exposed via an Agent Protocol-compatible API.

## Stack
- **Runtime**: Python 3.12+, managed with `uv`
- **Backend**: FastAPI + uvicorn
- **Agent framework**: LangGraph (MIT) — swap boundary is `AgentService`
- **LLM**: Anthropic Claude (`anthropic:claude-sonnet-4-20250514`)
- **Frontend**: Next.js (deep-agent-ui fork) at `frontend/`
- **Databases**: MariaDB (metadata), Neo4j (knowledge graph), Qdrant (vector search)

## Commands
```bash
./dev.sh                            # start backend (:8000) + frontend (:3000)
./stop.sh                           # stop both
uv run uvicorn backend.main:app --reload --port 8000   # backend only
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
  main.py               # FastAPI app, CORS, router registration
  config.py             # Settings (env prefix: SPRIH_)
  security/auth.py      # JWT decode → EnterpriseContext dependency
  routers/              # HTTP layer only
  schemas/              # Pydantic models
  handlers/             # Orchestration
  services/             # Business logic (DB, S3, agent execution)
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
The threads/runs/assistants API follows the LangGraph Platform API spec. Any client using `@langchain/langgraph-sdk` works against it. Custom business endpoints (`/sources`, `/artifacts`) are separate.

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
