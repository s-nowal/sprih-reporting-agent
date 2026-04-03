"""Run execution endpoints with SSE streaming (Agent Protocol compatible)."""

from uuid import uuid4

from fastapi import APIRouter, Depends, Response
from sse_starlette.sse import EventSourceResponse

from backend.handlers import run_handler
from backend.schemas.runs import RunCreate, RunResponse
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["runs"])


@router.post(
    "/threads/{thread_id}/runs",
    response_model=RunResponse,
    status_code=201,
)
async def create_run(
    thread_id: str,
    data: RunCreate,
    response: Response,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    result = await run_handler.create_run(thread_id, data, enterprise)
    # SDK parses Content-Location to extract run_id
    response.headers["Content-Location"] = (
        f"/threads/{thread_id}/runs/{result.run_id}"
    )
    return result


router.add_api_route(  # alias: /threads/{thread_id}/runs/create
    "/threads/{thread_id}/runs/create", create_run, methods=["POST"],
    include_in_schema=False,
)


@router.post("/threads/{thread_id}/runs/stream")
async def stream_run(
    thread_id: str,
    data: RunCreate,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Start a run and stream results as Server-Sent Events."""
    run_id = str(uuid4())

    async def event_generator():
        async for event in run_handler.stream_run(
            thread_id, data, enterprise, run_id=run_id
        ):
            yield event

    return EventSourceResponse(
        event_generator(),
        headers={"Content-Location": f"/threads/{thread_id}/runs/{run_id}"},
    )


@router.get(
    "/threads/{thread_id}/runs/{run_id}",
    response_model=RunResponse,
)
async def get_run(
    thread_id: str,
    run_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await run_handler.get_run(thread_id, run_id, enterprise)


@router.post(
    "/threads/{thread_id}/runs/{run_id}/cancel",
    response_model=RunResponse,
)
async def cancel_run(
    thread_id: str,
    run_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await run_handler.cancel_run(thread_id, run_id, enterprise)
