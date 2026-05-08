"""Google Drive ``MirrorProvider`` implementation.

Implements the ``MirrorProvider`` abstract primitives in terms of the
``GoogleDriveClient`` infrastructure wrapper. The shared sync orchestration
in :mod:`backend.services.mirror.base` does the rest.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from backend.infra.google_drive import (
    GoogleDriveClient,
    credentials_from_refresh_token,
)
from backend.models.mirror_credentials import MirrorCredentials
from backend.services.mirror.base import MirrorProvider

logger = logging.getLogger(__name__)


class GoogleDriveMirrorProvider(MirrorProvider):
    """``MirrorProvider`` backed by Google Drive (Drive v3 API).

    Builds a ``GoogleDriveClient`` lazily on first use. The client wraps a
    refreshable ``Credentials`` object, so token rotation is handled by
    ``google-auth`` underneath.

    Args:
        creds: ``MirrorCredentials`` row whose ``provider`` is
            ``"google_drive"``.
    """

    provider_name = "google_drive"

    def __init__(self, creds: MirrorCredentials) -> None:
        super().__init__(creds)
        self._client: GoogleDriveClient | None = None

    # -- Lazy client construction ------------------------------------------

    def _get_client(self) -> GoogleDriveClient:
        """Return the cached Drive client, building it on first call."""
        if self._client is None:
            scopes = self._creds.scopes.split() if self._creds.scopes else None
            oauth = credentials_from_refresh_token(
                refresh_token=self._creds.refresh_token, scopes=scopes
            )
            self._client = GoogleDriveClient(oauth)
        return self._client

    # -- MirrorProvider primitives -----------------------------------------

    def find_or_create_folder(self, parent_id: str, name: str) -> str:
        return self._get_client().find_or_create_folder(parent_id, name)

    def create_folder(self, parent_id: str, name: str) -> str:
        return self._get_client().create_folder(parent_id, name)

    def list_files_recursive(self, folder_id: str) -> list[dict[str, Any]]:
        return self._get_client().list_files_recursive(folder_id)

    def download_file(self, file_id: str) -> bytes:
        return self._get_client().download_file(file_id)

    def upload_new_file(
        self, parent_id: str, name: str, content: bytes, mime_type: str
    ) -> str:
        return self._get_client().upload_new_file(
            parent_id=parent_id, name=name, content=content, mime_type=mime_type
        )

    def update_file_content(
        self, file_id: str, content: bytes, mime_type: str
    ) -> None:
        self._get_client().update_file_content(file_id, content, mime_type)

    def get_folder_metadata(self, folder_id: str) -> dict[str, Any] | None:
        return self._get_client().get_file_metadata(folder_id)

    def is_native_format(self, mime_type: str) -> bool:
        # Native Google Docs / Sheets / Slides aren't real binary files —
        # downloading them returns nothing useful and uploading replacements
        # silently changes their type. Skip them in sync.
        return mime_type.startswith("application/vnd.google-apps.")

    def parse_modified_time(self, value: str | None) -> datetime | None:
        return GoogleDriveClient.parse_modified_time(value)

    # -- Convenience for the OAuth callback --------------------------------

    def get_authenticated_email(self) -> str:
        """Return the email of the account this provider authenticates as.

        Used by the OAuth callback to record which user authorized the app.

        Returns:
            Primary email address of the signed-in user.
        """
        return self._get_client().get_email()
