import asyncio
# from typing import dict

_sync_events: dict[str, asyncio.Event] = {}
_sync_results: dict[str, bytes] = {}

def get_or_create_event(thread_id: str) -> asyncio.Event:
    if thread_id not in _sync_events:
        _sync_events[thread_id] = asyncio.Event()
    return _sync_events[thread_id]

async def wait_for_sync(thread_id: str, timeout: float = 30.0) -> dict:
    print(f"[sync] wait_for_sync called for thread: {thread_id}")
    event = asyncio.Event()
    _sync_events[thread_id] = event

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        _sync_events.pop(thread_id, None)
        raise TimeoutError(f"Doc sync timed out for thread {thread_id}")

    _sync_events.pop(thread_id, None)
    return _sync_results.pop(thread_id)

def fulfill_sync(thread_id: str, data: dict) -> None:
    print(f"[sync] fulfill_sync called for thread: {thread_id}")
    print(f"[sync] active events: {list(_sync_events.keys())}")
    if thread_id not in _sync_events:
        print(f"No active sync for {thread_id}")
        return

    _sync_results[thread_id] = data
    _sync_events[thread_id].set()