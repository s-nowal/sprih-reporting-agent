"""Cite-source tool — copies a fetched source's original bytes into the workspace.

Wraps ``services.ingestion.store.copy_source_to_workspace``: pulls
``enterprise_id``, ``thread_id``, and ``job_id`` from the LangGraph
``RunnableConfig`` and delegates the validation, bronze read, and workspace
write to the service. Designed to be called by the research subagent after
it has grounded a Finding on a source — the resulting file lands at
``/research/citations/<filename>`` and is mirrored to Drive on the next sync.

Only the research subagent has this tool. The reporting agent does NOT, by
design: citation is the research agent's responsibility, and the tool
enforces ``data_source.job_id == current job_id`` so an agent cannot cite
arbitrary historical sources.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services.ingestion.store import copy_source_to_workspace


@tool
async def cite_source(
    source_id: str,
    *,
    config: RunnableConfig,
) -> dict[str, Any] | str:
    """Stage a fetched source as a citation for the final report.

    Copies the source's original bytes from bronze storage into this
    thread's ``research/citations/<filename>``. The filename is derived
    from the source URL with a short ``source_id`` prefix to avoid
    collisions. Web pages are written as ``.md``; binaries (PDFs, XLSX,
    …) are written in their original format so the user can open them
    directly from Drive.

    Restrictions:
    - You can only cite a ``source_id`` you fetched in this run (via
      ``web_fetch``). Citing a source from a prior run or a different
      enterprise will fail.
    - The tool is idempotent: calling it twice on the same ``source_id``
      returns ``already_existed=True`` and does not rewrite the file.

    Args:
        source_id: The ``source_id`` returned by ``web_fetch`` for the
            source you want to cite.

    Returns:
        On success, a dict with ``path`` (e.g.
        ``"/research/citations/8a4f_company-esg-2024.pdf"``),
        ``size_bytes``, ``source_ref``, ``source_type``, and
        ``already_existed: bool``. On failure (unknown id, wrong run,
        wrong enterprise, missing bronze content), returns a plain error
        string the agent should read and recover from (e.g. by trying a
        different ``source_id``).
    """
    configurable = config.get("configurable", {}) or {}
    enterprise_id = configurable.get("enterprise_id")
    thread_id = configurable.get("thread_id")
    job_id = configurable.get("job_id")

    if not enterprise_id or not thread_id:
        return (
            "Error: cite_source requires enterprise_id and thread_id in the "
            "run config — this should be set automatically by the agent service"
        )

    result = await copy_source_to_workspace(
        source_id,
        enterprise_id=enterprise_id,
        thread_id=thread_id,
        job_id=job_id,
    )
    if "error" in result:
        return f"Error: {result['error']}"
    return result
