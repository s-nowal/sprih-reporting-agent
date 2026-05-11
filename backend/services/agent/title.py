"""Thread title generator — derives a short title from the first user message.

Triggered by the run handler at the end of a thread's first run, when
``threads.metadata['title']`` is not yet set. Uses a fast Haiku model so
it adds minimal latency to the run-end path.
"""

from __future__ import annotations

import logging

from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)

_TITLE_MODEL = "anthropic:claude-haiku-4-5"

_SYSTEM_PROMPT = (
    "You generate concise titles for chat threads in an ESG reporting tool. "
    "Given the user's first message, return a 4-8 word title that captures "
    "the topic. No quotes, no trailing punctuation, no leading 'Title:'. "
    "Plain Title Case. Return only the title, nothing else."
)

_FALLBACK_MAX_LEN = 60


def _fallback_title(message: str) -> str:
    """Cheap deterministic title used when the LLM call fails.

    Takes the first ``_FALLBACK_MAX_LEN`` characters of the message, trims
    at the last whitespace boundary, and returns it. Always returns a
    non-empty string so the caller can persist it unconditionally.

    Args:
        message: The user's first message content.

    Returns:
        A short title string, never empty.
    """
    text = (message or "New conversation").strip().replace("\n", " ")
    if len(text) <= _FALLBACK_MAX_LEN:
        return text or "New conversation"
    truncated = text[:_FALLBACK_MAX_LEN]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated + "…"


async def generate_thread_title(first_user_message: str) -> str:
    """Generate a short thread title from the user's first message.

    Calls Haiku via ``init_chat_model``. On any failure (network, missing
    API key, empty response) falls back to a deterministic truncation so
    the caller never has to handle an exception or an empty title.

    Args:
        first_user_message: Plain-text content of the user's first message.

    Returns:
        A concise title string suitable for a chat-header / sidebar entry.
        Always non-empty.
    """
    text = (first_user_message or "").strip()
    if not text:
        return "New conversation"

    try:
        model = init_chat_model(model=_TITLE_MODEL, max_retries=2, timeout=15)
        resp = await model.ainvoke(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ]
        )
        content = (resp.content or "").strip()
        # Strip a leading/trailing quote if the model wrapped the title.
        content = content.strip("\"' ")
        # Drop a trailing period.
        if content.endswith("."):
            content = content[:-1].rstrip()
        if content:
            return content
        logger.warning("Title generator returned empty content; using fallback")
    except Exception as e:
        logger.warning("Title generation failed (%s); using fallback", e)

    return _fallback_title(text)
