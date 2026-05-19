"""Reporting Agent — top-level orchestrator for ESG report generation.

Uses ``create_deep_agent`` from the ``deepagents`` package which provides:
- Built-in file system tools (read, write, edit, ls, glob, grep)
- Subagent orchestration via ``CompiledSubAgent``
- Policy-based file access control (input/ and reference/ are read-only)

The Research Agent is wired as a ``CompiledSubAgent`` — its compiled
LangGraph graph is built fresh per-run inside ``build_reporting_graph``
because it needs the same ``workspace_prefix`` as the parent so the two
agents share a single S3-backed view of the thread workspace. The
research agent is allowed to write only under ``/research/``; the parent
has read-only access to that directory.

Storage is S3-style: the agent reads and writes through ``S3Backend``,
which talks to whatever ``get_storage()`` returns (today: ``LocalStorage``;
later: a real ``BotoS3Storage``). No local temp directory is involved.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from deepagents import CompiledSubAgent, create_deep_agent
from deepagents.backends.protocol import BackendProtocol, EditResult, WriteResult
from langchain.chat_models import init_chat_model

from backend.ai.agents.research_agent import build_research_graph
from backend.ai.prompts.agents.reporting import get_reporting_prompt
from backend.ai.tools.compile_results import compile_results
from backend.ai.tools.user_input import request_user_input
from backend.ai.tools.terminal_tools import run_terminal_command
from backend.infra.registry import get_storage
from backend.services.agent.s3_backend import S3Backend

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

# Read skill content once at import time — the file is static and small.
_PARSER_SKILL_MD = (
    Path(__file__).parent.parent / "skills" / "parser-skill" / "SKILL.md"
).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Policy wrapper — prevents writes to read-only directories
# ---------------------------------------------------------------------------

class _PolicyWrapper:
    """Wraps a backend to constrain which prefixes accept writes/edits.

    Two complementary policy modes can be combined on a single wrapper:

    - ``deny_prefixes``: writes and edits under any of these prefixes are
      blocked (read-only). Used by the parent reporting agent to lock
      ``input/``, ``reference/``, and ``research/``.
    - ``allow_only_prefixes``: writes and edits are blocked unless the
      target path falls under one of these prefixes. Used by the research
      subagent so it can only write inside ``/research/``.

    Args:
        inner: The underlying backend to delegate to.
        deny_prefixes: Directory prefixes where writes and edits are blocked
            (e.g. ``["input", "reference", "research"]``).
        allow_only_prefixes: When set, writes and edits are denied unless
            the target falls under one of these prefixes (e.g.
            ``["research"]``). ``None`` disables the allowlist check.
    """

    def __init__(
        self,
        inner: BackendProtocol,
        deny_prefixes: list[str] | None = None,
        allow_only_prefixes: list[str] | None = None,
    ) -> None:
        self.inner = inner
        self.deny = self._normalize(deny_prefixes or [])
        self.allow_only = self._normalize(allow_only_prefixes or []) or None

    @staticmethod
    def _normalize(prefixes: list[str]) -> list[str]:
        """Coerce prefixes to ``"/<name>/"`` form for prefix matching."""
        return [
            (p if p.startswith("/") else "/" + p).rstrip("/") + "/"
            for p in prefixes
        ]

    def __getattr__(self, name: str):
        """Delegate all non-overridden attribute access to the inner backend."""
        return getattr(self.inner, name)

    def _is_denied(self, path: str) -> bool:
        """True if ``path`` is blocked by either policy mode."""
        normalized = path if path.startswith("/") else "/" + path
        if any(normalized.startswith(p) for p in self.deny):
            return True
        if self.allow_only is not None and not any(
            normalized.startswith(p) for p in self.allow_only
        ):
            return True
        return False

    def write(self, file_path: str, content: str):
        """Block writes to denied directories, delegate otherwise."""
        if self._is_denied(file_path):
            return WriteResult(error=f"Denied: writes not allowed under '{file_path}'")
        return self.inner.write(file_path, content)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        """Block edits to denied directories, delegate otherwise."""
        if self._is_denied(file_path):
            return EditResult(error=f"Denied: edits not allowed under '{file_path}'")
        return self.inner.edit(file_path, old_string, new_string, replace_all)

    def ls_info(self, path: str):
        return self.inner.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return self.inner.read(file_path, offset=offset, limit=limit)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None):
        return self.inner.grep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/"):
        return self.inner.glob_info(pattern, path)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_reporting_graph(
    workspace_prefix: str,
    checkpointer: BaseCheckpointSaver | None = None,
    client_type: str = "browser",
):
    """Build and return the compiled reporting agent graph.

    A fresh graph is built per-run because the ``workspace_prefix`` differs
    for each thread. The research subagent is also built here (rather than
    at module import time) so it can be wired with an ``S3Backend`` rooted
    at the same workspace prefix — that way files the subagent writes under
    ``/research/`` are immediately visible to the parent's ``ls`` / ``read``
    / ``grep`` tools, and the parent's mirror sync picks them up for Drive.

    Args:
        workspace_prefix: Storage key prefix for this thread's workspace
            (e.g. ``"enterprise/{eid}/workspaces/{tid}"``). Every file
            operation issued by either agent is scoped under this prefix.
        checkpointer: Shared checkpointer for thread-scoped state persistence.
            Pass the same instance across all runs so the LLM sees the full
            conversation history on each turn.
        client_type: ``"word"`` for the Word add-in, ``"browser"`` (default)
            for the standard web UI. Selects the appropriate system prompt.

    Returns:
        A compiled LangGraph ``StateGraph`` ready for ``ainvoke`` / ``astream``.
    """
    # --- Seed skills into the workspace so the agent can discover them --------
    # S3Backend maps virtual paths "/..." to "{workspace_prefix}/..." in storage,
    # so writing here makes the file visible at /skills/parser-skill/SKILL.md
    # inside the agent's virtual filesystem.
    get_storage().write_text(
        f"{workspace_prefix}/skills/parser-skill/SKILL.md",
        _PARSER_SKILL_MD,
    )

    # --- Research subagent: shares the workspace, scoped to /research/ -------
    # The subagent gets its own S3Backend (same prefix as the parent) wrapped
    # in a policy that allows writes only under /research/. The cite_source
    # tool registered on the research graph writes citations directly via the
    # raw storage adapter (see backend/services/ingestion/store.py), so the
    # allowlist on the wrapper covers the agent's own write_file/edit_file
    # tool calls.
    researcher_subagent: CompiledSubAgent = {
        "name": "researcher-agent",
        "description": (
            "Performs detailed ESG research for a company and its peers. "
            "Call this subagent with the company name to search the web, "
            "crawl relevant pages, and generate research reports."
        ),
        "runnable": build_research_graph(
            checkpointer=None,
            backend=_PolicyWrapper(
                inner=S3Backend(storage=get_storage(), prefix=workspace_prefix),
                allow_only_prefixes=["research"],
            ),
        ),
    }

    return create_deep_agent(
        model=init_chat_model(
            model="anthropic:claude-sonnet-4-6",
            max_retries=10,
            timeout=300,
        ),
        subagents=[researcher_subagent],
        backend=lambda rt: _PolicyWrapper(
            inner=S3Backend(storage=get_storage(), prefix=workspace_prefix),
            deny_prefixes=["input", "reference", "research"],
        ),
        tools=[run_terminal_command, compile_results],
        skills=["/skills/"],
        checkpointer=checkpointer,
        system_prompt=get_reporting_prompt(client_type),
    )
