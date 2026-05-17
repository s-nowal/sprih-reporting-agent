"""System prompt for the Reporting Agent (main orchestrator).

The Reporting Agent is the top-level agent that drives the 5-phase ESG report
generation workflow.  It delegates research to the Research Agent (subagent)
and uses built-in file tools to manage workspace files.

Adapted from the reference implementation's ``system_prompt()`` in
``deep_agent_research/prompt.py``.

Use ``get_reporting_prompt(client_type)`` to select the correct variant:
- ``"browser"`` — standard web UI (Markdown + PDF output)
- ``"word"`` — Word add-in (DOCX-native output, content inserted into the active document)
"""

from .reporting_browser import _REPORTING_SYSTEM_PROMPT_BASE
from .reporting_word import _REPORTING_SYSTEM_PROMPT_WORD


def get_reporting_prompt(client_type: str = "browser") -> str:
    """Return the system prompt for the given client surface.

    Args:
        client_type: ``"word"`` for the Word add-in, ``"browser"`` (default)
            for the standard web UI.

    Returns:
        The assembled system prompt string.
    """
    if client_type == "word":
        return _REPORTING_SYSTEM_PROMPT_WORD
    return _REPORTING_SYSTEM_PROMPT_BASE
