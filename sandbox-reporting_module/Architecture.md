# Architecture

## Overview

ESG compliance reporting platform. Three data ingestion paths — **public web research** (cron), **enterprise data** (uploads + ERP auto-load), **internal research repositories** (team's ESG domain knowledge). Three agent layers — **Research**, **Extraction**, **Reporting** — connected by a medallion pipeline (bronze/silver/gold). Silver layer stores parsed documents in S3 and all extracted data in the **knowledge graph**. Gold layer is a KG cleanup (deduplication, entity resolution). Reporting Agent is user-facing and orchestrates the others as sub-agents. All user interaction is chat-style via threads/runs. Auth is external (main app issues JWTs with `enterprise_id`).

**Key architectural choices:**
- **Own FastAPI server** with `langgraph` library (MIT) as execution engine. No dependency on `langgraph-api` (Elastic License). Swap boundary is the service layer — if we replace langgraph later, only `AgentService` internals change.
- **Agent Protocol-compatible endpoints** (threads/runs) so `deep-agent-ui` works as frontend with minimal changes.
- **Repo mirrors production.** Only `infra/` adapters differ per environment. Sandbox: local filesystem (S3), MariaDB, local Neo4j, local Qdrant — all in Docker.

---

## Storage

### S3 (`/data/s3/` in sandbox, actual S3 in production)

```
/data/s3/
├── public/
│   ├── bronze/{source_id}/              # raw: web pages, PDFs, API responses
│   └── silver/{entity_id}/              # parsed document content (md/JSON)
│
├── enterprise/{eid}/
│   ├── bronze/
│   │   ├── uploads/{upload_id}/         # raw unstructured: PDF, Excel, DOCX, HTML
│   │   └── autoload/{source_system}/    # raw structured: ERP exports, API pulls
│   ├── silver/{entity_id}/              # parsed document content (md/JSON)
│   └── threads/{thread_id}/             # per-thread agent artifacts
│       ├── workspace/                   # intermediate working files
│       └── deliverables/                # final outputs (reports, questionnaires, DOCX/XLSX)
│
└── internal/
    ├── bronze/{batch_id}/               # raw research repo files (team's ESG findings)
    └── silver/                          # parsed domain knowledge documents
```

- **Bronze** = raw ingested, untouched.
- **Silver** = parsed documents in S3 + all extracted data as nodes/edges in KG (connected to entities).
- **Gold** = KG cleanup layer: deduplication, entity resolution, consistency checks. Not a separate S3 path — it's a state in Neo4j.

### MariaDB (container in sandbox, managed RDS in production)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `entities` | Companies/orgs being tracked | `id` (UUID), `name`, `type` (company/subsidiary/facility), `parent_id`, `external_ids` (JSON: LEI, CIN, DUNS), `is_public`, `enterprise_id` (nullable for public) |
| `data_sources` | Every ingested source with lineage | `id`, `entity_id`, `enterprise_id`, `source_type` (web/pdf/excel/erp/research_repo), `source_ref` (URL or filename), `s3_bronze_path`, `s3_silver_path`, `status` (fetched/extracting/extracted/failed), `fetched_at` |
| `threads` | Conversation threads (Agent Protocol) | `id` (UUID), `enterprise_id`, `status` (idle/busy/interrupted/error), `metadata` (JSON), `created_at`, `updated_at` |
| `runs` | Agent executions within threads | `id` (UUID), `thread_id` (FK), `agent_id`, `status` (pending/running/success/failed/interrupted), `input` (JSON), `output` (JSON), `created_at`, `completed_at` |
| `jobs` | All async work (report gen, research, extraction, cron) | `id`, `enterprise_id`, `thread_id` (FK, nullable), `job_type` (report_generation/research/extraction/cron_public/internal_research), `status` (queued/running/awaiting_feedback/completed/failed), `phase` (1-5 for reports), `config` (JSON), `created_at` |
| `deliverables` | Thread outputs (reports, questionnaires, etc.) | `id`, `thread_id` (FK), `enterprise_id`, `entity_id`, `type` (report/questionnaire/...), `format` (docx/xlsx/md), `status` (draft/review/approved/published), `s3_path`, `metadata` (JSON) |
| `lineage` | Audit trail: claim → source | `id`, `deliverable_id`, `claim_text`, `section_ref`, `source_id` (FK → data_sources), `source_location` (JSON: page, paragraph, table, cell), `extraction_method` (deterministic/llm), `confidence`, `llm_reasoning` |

`enterprises` table is managed by main app. AI backend receives enterprise context via JWT. `lineage` FK references `deliverables` instead of `reports`.

### Neo4j (Knowledge Graph)

**Nodes:**

| Label | Key properties |
|-------|---------------|
| `Entity` | id, name, type, sector, external_ids |
| `DataPoint` | id, value, unit, period, source_id, confidence |
| `Disclosure` | id, code (e.g. GRI 305-1), description |
| `Framework` | id, name (GRI/BRSR/CSRD), version |
| `Document` | id, name, type, s3_path |

**Edges:**

| Relationship | Between | Key properties |
|---|---|---|
| `OWNS` | Entity → Entity | ownership_pct, valid_from, valid_to |
| `REPORTED` | Entity → DataPoint | period |
| `EXTRACTED_FROM` | DataPoint → Document | page, location |
| `SATISFIES` | DataPoint → Disclosure | |
| `BELONGS_TO` | Disclosure → Framework | |
| `OPERATES_IN` | Entity → Geography | |

**Open design question**: how agents populate the KG. The extraction agent produces structured output that needs to become KG nodes/edges, but the mechanism (direct Cypher via tool, a KG ingestion service, batch import, etc.) is TBD.

### Qdrant (Vector DB)

Single collection `document_chunks`: embeddings of parsed document chunks.
Payload: `{source_id, entity_id, enterprise_id, chunk_text, page, section}`.
Used by agents for RAG — "what does source X say about emissions?"

---

## Repo Structure

```
├── pyproject.toml
├── .env.example
├── docker-compose.yml                   # local dev: MariaDB, Neo4j, Qdrant containers
│
├── src/
│   └── backend/
│       ├── __init__.py
│       ├── main.py                      # FastAPI app entry
│       ├── config.py                    # settings, env vars
│       │
│       ├── routers/
│       │   ├── threads.py               # thread CRUD (Agent Protocol)
│       │   ├── runs.py                  # run creation, SSE streaming, cancel
│       │   ├── documents.py             # data_sources upload, list, view
│       │   └── deliverables.py          # list + download thread outputs (reports, questionnaires, etc.)
│       │
│       ├── schemas/                     # Pydantic request/response models
│       │   ├── threads.py
│       │   ├── runs.py
│       │   ├── documents.py
│       │   └── deliverables.py
│       │
│       ├── handlers/                    # router ↔ service orchestration
│       │   ├── thread_handler.py
│       │   ├── run_handler.py
│       │   ├── document_handler.py
│       │   └── deliverable_handler.py
│       │
│       ├── services/                    # business logic (no HTTP awareness)
│       │   ├── agent_service.py         # wraps langgraph execution (THE SWAP POINT)
│       │   ├── thread_service.py        # thread CRUD in DB
│       │   ├── run_service.py           # run lifecycle, delegates to agent_service
│       │   ├── document_service.py      # upload processing, storage
│       │   ├── deliverable_service.py    # deliverable lifecycle (reports, questionnaires, etc.)
│       │   ├── research_service.py      # public data gathering + internal repo
│       │   ├── extraction_service.py    # raw → structured pipeline
│       │   ├── lineage_service.py       # audit trail CRUD
│       │   ├── entity_service.py        # resolution, search
│       │   └── export_service.py        # markdown → DOCX/XLSX
│       │
│       ├── ai/
│       │   ├── agents/
│       │   │   ├── reporting_agent.py       # orchestrator (user-facing)
│       │   │   ├── research_agent.py        # web research sub-agent
│       │   │   ├── extraction_agent.py      # document → structured data
│       │   │   ├── kg_explore_agent.py      # NL → Cypher queries
│       │   │   └── db_explore_agent.py      # structured DB + vector search
│       │   ├── tools/                       # agent-callable tools
│       │   │   ├── web_search.py
│       │   │   ├── web_crawl.py
│       │   │   ├── pdf_parse.py
│       │   │   ├── kg_query.py
│       │   │   ├── db_query.py
│       │   │   ├── file_ops.py
│       │   │   └── entity_resolve.py
│       │   ├── workflows/
│       │   │   ├── report_workflow.py       # 5-phase orchestration
│       │   │   └── research_workflow.py     # cron + internal repo pipeline
│       │   ├── single_call/                 # single LLM call tasks (no agent loop)
│       │   │   ├── summarize.py
│       │   │   ├── extract_metrics.py
│       │   │   └── entity_match.py
│       │   └── base/
│       │       ├── base_agent.py
│       │       ├── base_tool.py
│       │       └── prompts.py
│       │
│       ├── security/
│       │   └── auth.py                  # JWT validation, enterprise_id extraction
│       │
│       ├── infra/                       # infrastructure adapters (ONLY swap layer)
│       │   ├── storage.py               # S3 interface (local fs in sandbox, boto3 in prod)
│       │   ├── db.py                    # MariaDB connection (container in sandbox, managed in prod)
│       │   ├── kg.py                    # Neo4j connection
│       │   ├── vector.py               # Qdrant connection
│       │   └── scheduler.py            # cron runner (APScheduler in sandbox, managed in prod)
│       │
│       └── models/                      # ORM models (SQLAlchemy)
│           ├── entity.py
│           ├── data_source.py
│           ├── thread.py
│           ├── run.py
│           ├── job.py
│           ├── deliverable.py
│           └── lineage.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── frontend/                            # deep-agent-ui fork (chat-based UI)
│   └── ...                              # speaks Agent Protocol, talks to our FastAPI
│
├── data/                                # sandbox simulation mount (gitignored)
│   ├── s3/                              # simulated S3
│   └── seed/                            # seed data for dev/testing
│
├── scripts/
│   ├── seed_db.py                       # initialize DB schema + seed data
│   └── run_internal_research.py         # manual trigger for internal research repo
│
└── docker/
    ├── Dockerfile
    └── docker-compose.dev.yml           # MariaDB + Neo4j + Qdrant for local dev
```

**Swap boundary**: `infra/` is the only directory that differs between sandbox and production. `AgentService` is the only class that touches `langgraph` directly — everything above codes against its interface.

---

## API Endpoints

Agent Protocol-compatible thread/run endpoints + resource CRUD.

**Threads (conversation containers):**
```
POST   /threads                              # create thread
GET    /threads                              # list threads (filtered by enterprise)
GET    /threads/{id}                         # get thread state
PATCH  /threads/{id}                         # update metadata
DELETE /threads/{id}                         # delete thread
```

**Runs (agent executions within a thread):**
```
POST   /threads/{id}/runs                    # start run (background)
POST   /threads/{id}/runs/stream             # start run + SSE stream
GET    /threads/{id}/runs/{run_id}           # get run status
POST   /threads/{id}/runs/{run_id}/cancel    # cancel run
```

Resume from interrupt (human-in-the-loop):
```
POST   /threads/{id}/runs/stream             # with body: {command: {resume: value}}
```

**Data sources (document management):**
```
POST   /data_sources/upload                  # upload enterprise files
GET    /data_sources                         # list sources (filtered by enterprise)
GET    /data_sources/{id}                    # source metadata
```

**Deliverables (thread outputs — reports, questionnaires, etc.):**
```
GET    /deliverables                         # list deliverables (filtered by enterprise/thread)
GET    /deliverables/{id}                    # metadata + preview
GET    /deliverables/{id}/download           # DOCX/XLSX/PDF file
```

All endpoints receive enterprise context from `Authorization: Bearer <jwt>`. Audit trail queries are handled via conversation — user asks the agent, agent uses lineage tools internally.

---

## Agent Architecture

Own FastAPI handles HTTP. `langgraph` (MIT) handles graph execution. `AgentService` wraps the boundary.

```
  FastAPI (ours)                          langgraph (MIT)
┌──────────────────┐                   ┌─────────────────────┐
│ Router → Handler │──► AgentService ──►│  graph.ainvoke()    │
│                  │    (swap point)    │  graph.astream()    │
│ Auth middleware   │                   │  checkpointers      │
│ Thread/Run CRUD  │                   │  interrupt/resume   │
└──────────────────┘                   └─────────────────────┘
```

```
                        ┌─────────────────────┐
                        │   Reporting Agent    │  ← user thread
                        │   (orchestrator)     │
                        └──┬──┬──┬──┬─────────┘
                           │  │  │  │
              ┌────────────┘  │  │  └────────────┐
              ▼               ▼  ▼               ▼
        ┌───────────┐  ┌────────────┐  ┌──────────────┐
        │ Research   │  │ KG Explore │  │ DB Explore   │
        │ Agent      │  │ Agent      │  │ Agent        │
        └───────────┘  └────────────┘  └──────────────┘
              │
              ▼
        ┌───────────┐
        │ Extraction │
        │ Agent      │
        └───────────┘
```

- **Reporting Agent**: maintains conversation, plans report, writes sections, creates lineage records. Orchestrates sub-agents.
- **Research Agent**: given company + questions, searches web, crawls pages, downloads PDFs. Writes to bronze.
- **Extraction Agent**: given raw documents, extracts structured data (tables, facts, relationships). Writes to silver. KG population mechanism TBD.
- **KG Explore Agent**: translates natural language to Cypher, queries Neo4j.
- **DB Explore Agent**: searches MariaDB + Qdrant vector DB.

For cron/internal flows, Research Agent and Extraction Agent are invoked directly by services (not through Reporting Agent).

**Auth context flow**: JWT → middleware extracts `enterprise_id` → passed into graph via `config["configurable"]` → every agent/tool scopes queries by `enterprise_id`.

---

## Flows

### Flow 1: Document Upload (enterprise)

```
User ─► POST /data_sources/upload (files + metadata)
         │
    Router (documents.py)
         │
    DocumentHandler
         ├─► DocumentService.store()
         │     ├─ save to enterprise/{eid}/bronze/uploads/{upload_id}/
         │     └─ insert data_sources row (status=fetched)
         │
         └─► ExtractionService.enqueue(source_id)
               ├─ create job (type=data_extraction)
               └─ AgentService.invoke(extraction_agent, ...)
                    ├─ parse document → structured content (md/JSON)
                    ├─ write to enterprise/{eid}/silver/{entity_id}/
                    ├─ update data_sources (status=extracted)
                    ├─ EntityService.resolve() — match/create entity
                    ├─ populate KG (mechanism TBD)
                    └─ index chunks in Qdrant
```

### Flow 2: Enterprise Structured Data Auto-Load

```
ERP / external system ─► data lands in enterprise/{eid}/bronze/autoload/{source_system}/
         │
    DocumentService.detect_autoload() (watcher or periodic check)
         ├─ insert data_sources row (source_type=erp)
         └─► ExtractionService.enqueue(source_id)
               └─ (same extraction pipeline as Flow 1, but source is already structured)
                    ├─ normalize → silver/{entity_id}/
                    ├─ EntityService.resolve()
                    └─ populate KG
```

### Flow 3: Report Generation (5-phase, chat-style)

```
User ─► POST /threads (creates conversation thread)
User ─► POST /threads/{id}/runs/stream {agent_id: "reporting-agent", input: {messages: [...]}}
         │
    Router (runs.py)
         │
    RunHandler
         ├─► ThreadService.get(thread_id) — verify ownership
         ├─► RunService.create(thread_id, agent_id, input)
         │     ├─ create run record (status=running)
         │     ├─ create job (type=report_generation, phase=1)
         │     └─ create deliverable (type=report, status=draft)
         │
         └─► AgentService.stream(reporting_agent, thread_id, input)
               └─ SSE stream back to client
```

**Phase 1 — Context Gathering**
```
Reporting Agent
  ├─ query KG + VectorDB for existing data on target entity
  ├─ assess data adequacy
  ├─ if inadequate → delegate to Research Agent (sub-agent)
  │    ├─ Research Agent → web_search, web_crawl → bronze
  │    └─ Extraction Agent → bronze → silver → KG
  └─ reply in thread: "Here's what I found. Proposing outline..."
```

**Phase 2 — Index Proposal**
```
Reporting Agent
  ├─ propose report structure (sections, framework candidates)
  ├─ call interrupt() with proposed outline
  └─ thread status → "interrupted"
      │
User ─► POST /threads/{id}/runs/stream {command: {resume: {approved: true, edits: [...]}}}
      │
Reporting Agent ─► receives resume value, adjusts structure, proceeds
```

**Phase 3 — Data Collection & Validation**
```
Reporting Agent
  ├─ for each section: gather specific data points
  │    ├─ KG Explore Agent → Cypher queries
  │    ├─ DB Explore Agent → MariaDB + Qdrant
  │    └─ if gaps → Research Agent → fill gaps
  ├─ gap analysis → interrupt() for user input
  └─ user provides missing info or approves best-effort
```

**Phase 4 — Draft & Feedback**
```
Reporting Agent
  ├─ write section drafts as markdown → enterprise/{eid}/threads/{tid}/workspace/
  ├─ create lineage records (claim → source, page, confidence)
  ├─ interrupt() with sections for review
  │
User ─► resume with feedback per section
  │
Reporting Agent ─► revise, update lineage
```

**Phase 5 — Final Publication**
```
Reporting Agent
  ├─ finalize all sections
  ├─ ExportService.convert(deliverable_id)
  │    └─ markdown → DOCX/XLSX → enterprise/{eid}/threads/{tid}/deliverables/
  ├─ update deliverable (status=published)
  └─ update job (status=completed)
```

### Flow 4: Audit Trail Query

User asks in conversation: "Where did the 98.4% renewable energy figure come from?"

```
Reporting Agent
  ├─ uses lineage tool internally
  │    ├─ query lineage table for matching claim
  │    ├─ join data_sources for source metadata
  │    └─ return: {claim, source, page/location, extraction_method, confidence, reasoning}
  └─ responds in thread with full audit trail
```

Also available as static export: full lineage embedded in deliverable DOCX appendix.

### Flow 5: Cron — Public Data Refresh

```
Scheduler (periodic, e.g. daily)
         │
    ResearchService.refresh_public()
         ├─ load entity list (where is_public=true)
         ├─ create job (type=cron_public_fetch)
         │
         └─ for each entity:
              ├─ AgentService.invoke(research_agent, ...)
              │    └─ web_search, web_crawl → public/bronze/{source_id}/
              │    └─ insert data_sources rows
              │
              ├─ AgentService.invoke(extraction_agent, ...)
              │    ├─ public/silver/{entity_id}/
              │    ├─ populate KG
              │    └─ index in Qdrant
              │
              └─ update job status on completion
```

### Flow 6: Internal Research Repository Processing

```
Team member ─► runs scripts/run_internal_research.py (manual trigger)
         │
    ResearchService.process_internal_repo(folder_path)
         ├─ create job (type=internal_research)
         ├─ scan folder → insert data_sources rows (source_type=research_repo)
         ├─ copy files to internal/bronze/{batch_id}/
         │
         └─ AgentService.invoke(extraction_agent, ...) per file
              ├─ extract domain knowledge (ESG standards, methodologies, sector guidance)
              ├─ write to internal/silver/
              ├─ populate KG with domain knowledge nodes
              └─ index in Qdrant
```

This flow embeds the team's ESG expertise into the knowledge graph so agents have domain context when extracting data or generating reports.

---

## Key Design Decisions

1. **Own FastAPI + langgraph (MIT)**: we own the HTTP and persistence layers. `langgraph` library is the execution engine, swappable via `AgentService`. No Elastic License dependency.
2. **Agent Protocol-compatible**: thread/run endpoints follow the standard so `deep-agent-ui` and other Agent Protocol clients work with minimal changes.
3. **Framework-agnostic**: agent converges on framework with customer during Phase 2. No hardcoded framework logic.
4. **Silver/Gold are KG layers**: Silver KG has all extracted data connected to entities. Gold KG is deduplicated, entity-resolved, cleaned. S3 silver stores parsed documents only.
5. **Entity resolution is LLM-assisted**: public data has no reliable identifiers. LLM matches entities, assigns internal UUIDs, maps external IDs when found.
6. **Lineage is dual-mode**: deterministic (page/table reference) where possible, LLM-extracted (with confidence + reasoning) otherwise. Both stored. Queried via conversation, exported in report appendix.
7. **Data isolation**: all queries filter by `enterprise_id`. Public data (`enterprise_id=null`) is shared. Private data is never cross-accessible. Thread ownership enforced via auth.
8. **KG population mechanism TBD**: extraction agent produces structured output, but how it becomes KG nodes/edges is an open design question.
9. **Three ingestion paths**: public (cron), enterprise (upload + ERP auto-load), internal research (team-triggered). All converge on the same silver → KG pipeline.
10. **Sub-agents, not microservices**: agents run in-process via LangGraph delegation (for report flow) or direct service invocation (for cron/internal flows).
