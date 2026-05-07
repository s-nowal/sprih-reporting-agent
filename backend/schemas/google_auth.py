"""Pydantic models for the /auth/google router."""

from pydantic import BaseModel


class StartAuthResponse(BaseModel):
    """Body returned by ``GET /auth/google/start``.

    Attributes:
        authorize_url: The Google consent screen URL the caller should open
            in a browser. After consent, Google redirects back to
            ``/auth/google/callback`` with an authorisation code.
        enterprise_id: Echoed for clarity — the same id the redirect carries
            in its ``state`` parameter.
    """

    authorize_url: str
    enterprise_id: str


class StatusResponse(BaseModel):
    """Body returned by ``GET /auth/google/status``.

    Attributes:
        connected: ``True`` if a refresh token has been stored.
        agent_email: Google account the refresh token is for, if connected.
        drive_parent_folder_id: Drive ID of the shared "Sprih" parent folder,
            if configured.
    """

    connected: bool
    agent_email: str | None = None
    drive_parent_folder_id: str | None = None


class SetParentFolderRequest(BaseModel):
    """Body for ``POST /auth/google/parent-folder``.

    Attributes:
        drive_parent_folder_id: Drive folder ID of the shared "Sprih" folder
            the agent should use for this enterprise.
    """

    drive_parent_folder_id: str
