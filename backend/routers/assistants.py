"""Assistant endpoints — stub for SDK/frontend compatibility."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.schemas.assistants import AssistantResponse, AssistantSearch

router = APIRouter(tags=["assistants"])

ASSISTANTS: dict[str, AssistantResponse] = {
    "research-agent": AssistantResponse(
        assistant_id="research-agent",
        graph_id="research-agent",
        name="ESG Research Agent",
        config={},
        metadata={"created_by": "system"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ),
    "reporting-agent": AssistantResponse(
        assistant_id="reporting-agent",
        graph_id="reporting-agent",
        name="ESG Reporting Agent",
        config={},
        metadata={"created_by": "system"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ),
}


@router.get("/assistants/{assistant_id}", response_model=AssistantResponse)
async def get_assistant(assistant_id: str):
    assistant = ASSISTANTS.get(assistant_id)
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")
    return assistant


@router.post("/assistants/search", response_model=list[AssistantResponse])
async def search_assistants(data: AssistantSearch = AssistantSearch()):
    results = list(ASSISTANTS.values())
    if data.graph_id:
        results = [a for a in results if a.graph_id == data.graph_id]
    if data.metadata:
        results = [
            a for a in results
            if all(a.metadata.get(k) == v for k, v in data.metadata.items())
        ]
    return results[data.offset : data.offset + data.limit]
