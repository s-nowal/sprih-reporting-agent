"""Reporting Agent — top-level orchestrator for ESG report generation.

Uses ``create_deep_agent`` from the ``deepagents`` package which provides:
- Built-in file system tools (read, write, edit, ls, glob, grep)
- Subagent orchestration via ``CompiledSubAgent``
- Policy-based file access control (input/ and reference/ are read-only)

The Research Agent is wired as a ``CompiledSubAgent`` — its compiled
LangGraph graph is passed directly via the ``runnable`` key, so the
research agent's definition lives in one place (``research_agent.py``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from deepagents import CompiledSubAgent, create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import EditResult, WriteResult
from langchain.chat_models import init_chat_model

from backend.ai.agents.research_agent import build_research_graph
from backend.ai.prompts.agents.user_spec import USER_TONE_SPECIFICATION
from backend.ai.prompts.agents.reporting import REPORTING_SYSTEM_PROMPT
from backend.ai.prompts.agents.parser import PARSER_AGENT_PROMPT
from backend.ai.tools.user_input import request_user_input
from backend.ai.tools.generate_report import send_report_to_user
from backend.ai.tools.terminal_tools import upload_full_directory, run_terminal_command, add_file_to_local

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

# ---------------------------------------------------------------------------
# Policy wrapper — prevents writes to read-only directories
# ---------------------------------------------------------------------------

class _PolicyWrapper:
    """Wraps a ``FilesystemBackend`` to deny writes under specified prefixes
    and mirror every allowed write to actual disk alongside the virtual store.

    Args:
        inner: The underlying backend to delegate to.
        deny_prefixes: Directory prefixes where writes and edits are blocked
            (e.g. ``["input", "reference"]``).
        disk_root: Workspace root on disk. Every allowed write is also written
            here so the workspace folder is populated without disabling virtual
            mode on the inner backend.
    """

    def __init__(
        self,
        inner: FilesystemBackend,
        deny_prefixes: list[str],
        disk_root: Path,
    ) -> None:
        self.inner = inner
        self.disk_root = disk_root
        self.deny = [
            (p if p.startswith("/") else "/" + p).rstrip("/") + "/"
            for p in deny_prefixes
        ]

    def __getattr__(self, name: str):
        """Delegate all non-overridden attribute access to the inner backend."""
        return getattr(self.inner, name)

    def _is_denied(self, path: str) -> bool:
        normalized = path if path.startswith("/") else "/" + path
        return any(normalized.startswith(p) for p in self.deny)

    def _mirror_to_disk(self, file_path: str, content: str) -> None:
        actual = self.disk_root / file_path.lstrip("/")
        actual.parent.mkdir(parents=True, exist_ok=True)
        actual.write_text(content, encoding="utf-8")

    def write(self, file_path: str, content: str):
        """Block writes to denied directories; mirror allowed writes to disk."""
        if self._is_denied(file_path):
            return WriteResult(error=f"Denied: writes not allowed under '{file_path}'")
        result = self.inner.write(file_path, content)
        self._mirror_to_disk(file_path, content)
        return result

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False):
        """Block edits to denied directories; mirror allowed edits to disk."""
        if self._is_denied(file_path):
            return EditResult(error=f"Denied: edits not allowed under '{file_path}'")
        result = self.inner.edit(file_path, old_string, new_string, replace_all)
        # Re-read the updated virtual content and mirror it
        try:
            updated = self.inner.read(file_path)
            if hasattr(updated, "content"):
                self._mirror_to_disk(file_path, updated.content)
            elif isinstance(updated, str):
                self._mirror_to_disk(file_path, updated)
        except Exception:
            pass
        return result

    def ls_info(self, path: str):
        return self.inner.ls_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000):
        return self.inner.read(file_path, offset=offset, limit=limit)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None):
        return self.inner.grep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/"):
        return self.inner.glob_info(pattern, path)


# ---------------------------------------------------------------------------
# Subagent definitions
# ---------------------------------------------------------------------------
# The research agent is built as a compiled LangGraph graph and passed via
# CompiledSubAgent. No checkpointer needed — the parent agent manages state.

_researcher_subagent: CompiledSubAgent = {
    "name": "researcher-agent",
    "description": (
        "Performs detailed ESG research for a company and its peers. "
        "Call this subagent with the company name to search the web, "
        "crawl relevant pages, and generate research reports."
    ),
    "runnable": build_research_graph(checkpointer=None),
}

parser_subagent = {
    "name": "parser-agent",
    "description": "Converts any document from the filesystem into the requested format. Has code writing and execution capability with filesystem access.",
    "system_prompt": PARSER_AGENT_PROMPT,
    "tools": [upload_full_directory, run_terminal_command, add_file_to_local],
}

# user_specs_subagent = {
#     "name": "get_user_specs",
#     "description": "Interacts with user to get specifications for tone and intent of the report.",
#     "system_prompt": USER_TONE_SPECIFICATION,
#     "tools": [write_md_report, request_user_input],
# }

# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_reporting_graph(
    workspace_root: Path,
    checkpointer: BaseCheckpointSaver | None = None,
):
    """Build and return the compiled reporting agent graph.

    A fresh graph is built per-run because the ``workspace_root`` differs
    for each thread (isolated temp directory).  This is cheap — it just
    wires nodes and edges; the checkpointer is a shared singleton passed in
    by the caller so conversation history persists across runs.

    Args:
        workspace_root: Absolute path to the temp workspace directory for
            this run. Must contain input/, workspace/, output/, reference/
            subdirectories.
        checkpointer: Shared checkpointer for thread-scoped state persistence.
            Pass the same instance across all runs so the LLM sees the full
            conversation history on each turn.

    Returns:
        A compiled LangGraph ``StateGraph`` ready for ``ainvoke`` / ``astream``.
    """
    return create_deep_agent(
        model=init_chat_model(
            model="anthropic:claude-sonnet-4-6",
            max_retries=10,
            timeout=1200,
        ),
        subagents=[_researcher_subagent, parser_subagent],
        backend=lambda rt: _PolicyWrapper(
            inner=FilesystemBackend(root_dir=workspace_root, virtual_mode=True),
            deny_prefixes=["input", "reference"],
            disk_root=workspace_root,
        ),
        skills=["./skills"],
        tools=[send_report_to_user],
        checkpointer=checkpointer,
        system_prompt=REPORTING_SYSTEM_PROMPT,
    )