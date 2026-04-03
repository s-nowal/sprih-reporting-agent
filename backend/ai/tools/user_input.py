"""User input tool — pauses the agent and waits for human response.

Uses LangGraph's ``interrupt()`` primitive to suspend graph execution.
The run handler detects the interrupt and yields it as an SSE event.
The frontend collects the user's response and sends it back via
``Command(resume=...)`` to continue execution.
"""

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def request_user_input(message: str) -> str:
    """Send a message to the user and wait for their response.

    You MUST use this tool whenever you need the user to review, confirm,
    or provide information.  The agent cannot proceed without calling this
    tool — do not write output as a message and continue.  This is the
    only channel to communicate with the user mid-task.

    Args:
        message: The message or question to present to the user.

    Returns:
        The user's response as a string.
    """
    response = interrupt({"message": message})
    return str(response)
