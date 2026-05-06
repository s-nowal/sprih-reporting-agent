"""Business logic layer (no HTTP awareness).

Sub-packages:
- agent: AgentService (LangGraph abstraction), thread, workspace
- ingestion: search, crawl, bronze storage, source
- extraction: parsing, pipeline, export (bronze → silver → KG)
- embedding: vector indexing (Qdrant)

Flat modules:
- job: cross-cutting job lifecycle (agentic + non-agentic flows)
- lineage: audit trail CRUD (pending)
- entity: entity resolution and search (pending)
"""