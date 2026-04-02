"""Assistant endpoints — stub for SDK/frontend compatibility."""

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["assistants"])

ASSISTANTS = {
    "reporting-agent": {
        "assistant_id": "reporting-agent",
        "graph_id": "reporting-agent",
        "name": "ESG Reporting Agent",
        "config": {},
        "metadata": {"created_by": "system"},
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "version": 1,
    }
}


@router.get("/assistants/{assistant_id}")
async def get_assistant(assistant_id: str):
    if assistant_id in ASSISTANTS:
        return ASSISTANTS[assistant_id]
    return {"detail": "Not found"}, 404


@router.post("/assistants/search")
async def search_assistants(body: dict = {}):
    graph_id = body.get("graph_id")
    results = ASSISTANTS.values()
    if graph_id:
        results = [a for a in results if a["graph_id"] == graph_id]
    return list(results)
