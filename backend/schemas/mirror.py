"""Schemas for the per-thread mirror endpoints (``/threads/{tid}/mirror``)."""

from pydantic import BaseModel, Field


class LinkMirrorRequest(BaseModel):
    """Body of ``PUT /threads/{tid}/mirror`` — link the thread to a new folder.

    Fields:
        folder_name: Display name to use when creating the provider-side
            folder. The folder is created fresh under the configured
            agent parent (existing folders with the same name are not
            looked up — Drive allows duplicates).
        agent_name: Graph name the thread belongs to. Determines which
            parent subfolder the new folder lives under and which
            workspace subdirs are mirrored. Defaults to the only agent
            we ship today.
        if_broken: When ``True``, allow re-linking even if the thread
            already has a mapping — but only if the existing folder is
            broken (deleted/trashed in Drive). The handler still rejects
            re-link requests against a healthy mapping.
    """

    folder_name: str = Field(min_length=1, max_length=200)
    agent_name: str = Field(default="reporting-agent")
    if_broken: bool = Field(default=False)


class MirrorLinkResponse(BaseModel):
    """Outcome of a successful link / re-link."""

    provider: str
    folder_id: str
    folder_name: str


class MirrorStatusResponse(BaseModel):
    """Body of ``GET /threads/{tid}/mirror`` — current linkage state.

    Fields:
        linked: ``True`` iff a mapping row exists for this thread.
        provider: Provider key when linked.
        folder_id: Provider folder id when linked.
        folder_name: Cached folder display name. ``None`` when the link
            is broken (we couldn't fetch live metadata).
        is_broken: ``True`` when the linked folder no longer resolves
            on the provider (404 / trashed). UI uses this to enable the
            re-link form.
    """

    linked: bool
    provider: str | None = None
    folder_id: str | None = None
    folder_name: str | None = None
    is_broken: bool = False
