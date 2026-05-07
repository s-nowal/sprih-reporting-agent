"""Google Drive API wrapper.

Thin convenience layer over the ``googleapiclient`` Drive v3 service. Pure
I/O — no business logic, no DB access. The sync service composes these
primitives into the per-turn sync_in / sync_out workflows.

The wrapper accepts an OAuth ``Credentials`` object built from a refresh
token (the long-lived secret stored per enterprise in ``mirror_credentials``).
Access tokens are minted automatically by the underlying library.

The Drive API is **synchronous**. Callers should run ``GoogleDriveClient``
methods in a thread (``asyncio.to_thread``) so they don't block the event
loop. The shared sync orchestration in
:mod:`backend.services.mirror.base` does this for the provider primitives.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from backend.config import settings

logger = logging.getLogger(__name__)

# Scope set the agent always requests. ``drive.file`` lets the agent see
# files it created or that were explicitly shared with it — perfect for the
# "enterprise-shared Sprih folder" model since the parent folder is shared
# by the user / enterprise admin and everything inside is then visible.
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


def credentials_from_refresh_token(refresh_token: str, scopes: list[str] | None = None) -> Credentials:
    """Build a ``Credentials`` object from a stored refresh token.

    The credentials object refreshes the access token on demand using the
    OAuth client id/secret from settings.

    Args:
        refresh_token: The long-lived refresh token stored per enterprise.
        scopes: OAuth scopes the token was issued with. Defaults to
            ``DRIVE_SCOPES``.

    Returns:
        ``google.oauth2.credentials.Credentials`` ready to pass to
        ``googleapiclient.discovery.build``.

    Raises:
        ValueError: If ``settings.google_oauth_client_id`` /
            ``google_oauth_client_secret`` are not configured.
    """
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise ValueError(
            "Google OAuth client not configured — set "
            "SPRIH_GOOGLE_OAUTH_CLIENT_ID and SPRIH_GOOGLE_OAUTH_CLIENT_SECRET."
        )

    return Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret,
        scopes=scopes or DRIVE_SCOPES,
    )


class GoogleDriveClient:
    """Thin wrapper around the Drive v3 service.

    Construct with a refreshable ``Credentials`` object. All methods are
    blocking — wrap calls in ``asyncio.to_thread`` from async contexts.

    Args:
        credentials: An OAuth ``Credentials`` object. See
            :func:`credentials_from_refresh_token`.
    """

    def __init__(self, credentials: Credentials) -> None:
        self._creds = credentials
        # ``cache_discovery=False`` avoids a noisy warning when the on-disk
        # discovery cache directory isn't writable.
        self._service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    # -- Auth ----------------------------------------------------------------

    def get_email(self) -> str:
        """Return the email address of the authenticated user.

        Useful at OAuth callback time to record which account the refresh
        token belongs to.

        Returns:
            The primary email address of the signed-in user.
        """
        about = self._service.about().get(fields="user(emailAddress)").execute()
        return about["user"]["emailAddress"]

    # -- Folder operations --------------------------------------------------

    def find_child_folder(self, parent_id: str, name: str) -> str | None:
        """Find a direct child folder by exact name under ``parent_id``.

        Args:
            parent_id: Drive ID of the parent folder.
            name: Exact folder name to look for. Single quotes are escaped.

        Returns:
            The matching folder's Drive ID, or ``None`` if no folder with
            that name exists directly under the parent.
        """
        safe_name = name.replace("'", r"\'")
        q = (
            f"'{parent_id}' in parents and "
            f"mimeType = 'application/vnd.google-apps.folder' and "
            f"name = '{safe_name}' and trashed = false"
        )
        resp = self._service.files().list(
            q=q,
            fields="files(id, name)",
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        files = resp.get("files", [])
        return files[0]["id"] if files else None

    def create_folder(self, parent_id: str, name: str) -> str:
        """Create a folder named ``name`` under ``parent_id`` and return its id.

        Does *not* check for duplicates — Drive permits multiple folders with
        the same name in the same parent. Use :meth:`find_or_create_folder`
        to dedupe by name.

        Args:
            parent_id: Drive ID of the parent folder.
            name: New folder's display name.

        Returns:
            The new folder's Drive ID.
        """
        body = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        folder = self._service.files().create(
            body=body,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return folder["id"]

    def find_or_create_folder(self, parent_id: str, name: str) -> str:
        """Idempotent variant of :meth:`create_folder`.

        Args:
            parent_id: Drive ID of the parent folder.
            name: Display name of the folder to find or create.

        Returns:
            Drive ID of the existing or newly-created folder.
        """
        existing = self.find_child_folder(parent_id, name)
        if existing:
            return existing
        return self.create_folder(parent_id, name)

    def rename_file(self, file_id: str, new_name: str) -> None:
        """Rename a file or folder.

        Args:
            file_id: Drive ID of the item to rename.
            new_name: New display name.
        """
        self._service.files().update(
            fileId=file_id,
            body={"name": new_name},
            supportsAllDrives=True,
        ).execute()

    # -- File listing -------------------------------------------------------

    def list_files_recursive(
        self, folder_id: str, _prefix: str = ""
    ) -> list[dict[str, Any]]:
        """Walk a folder tree and return all files (not folders).

        For each file, returns a dict with ``id``, ``name``, ``mimeType``,
        ``modifiedTime`` (ISO 8601 string), ``size`` (bytes as int, may be
        ``None`` for native Google Docs), and ``relative_path`` — the path
        from ``folder_id`` joined with forward slashes.

        Args:
            folder_id: Drive ID of the root folder to walk.
            _prefix: Internal — accumulated path components for recursion.

        Returns:
            Flat list of file metadata dicts. Folders are descended into but
            not included themselves.
        """
        results: list[dict[str, Any]] = []

        page_token: str | None = None
        while True:
            resp = self._service.files().list(
                q=f"'{folder_id}' in parents and trashed = false",
                fields=(
                    "nextPageToken, files(id, name, mimeType, modifiedTime, size)"
                ),
                pageSize=200,
                pageToken=page_token,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()

            for item in resp.get("files", []):
                child_path = f"{_prefix}/{item['name']}" if _prefix else item["name"]
                if item["mimeType"] == "application/vnd.google-apps.folder":
                    results.extend(
                        self.list_files_recursive(item["id"], child_path)
                    )
                else:
                    results.append(
                        {
                            "id": item["id"],
                            "name": item["name"],
                            "mimeType": item["mimeType"],
                            "modifiedTime": item.get("modifiedTime"),
                            "size": int(item["size"]) if item.get("size") else None,
                            "relative_path": child_path,
                        }
                    )

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return results

    # -- File transfer ------------------------------------------------------

    def download_file(self, file_id: str) -> bytes:
        """Download the binary contents of a Drive file.

        Does *not* support native Google Docs — those require ``files.export``.
        We deliberately don't handle them; the agent only writes binary
        formats and the sync service skips ``application/vnd.google-apps.*``
        mime types.

        Args:
            file_id: Drive ID of the file to download.

        Returns:
            The file's bytes.
        """
        request = self._service.files().get_media(
            fileId=file_id, supportsAllDrives=True
        )
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()

    def upload_new_file(
        self, parent_id: str, name: str, content: bytes, mime_type: str
    ) -> str:
        """Create a new file in ``parent_id`` with the given bytes.

        Args:
            parent_id: Drive folder ID to create the file in.
            name: File name (basename only, no path).
            content: File contents as bytes.
            mime_type: MIME type to register the file with.

        Returns:
            Drive ID of the newly created file.
        """
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
        body = {"name": name, "parents": [parent_id]}
        f = self._service.files().create(
            body=body,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return f["id"]

    def update_file_content(
        self, file_id: str, content: bytes, mime_type: str
    ) -> None:
        """Replace the contents of an existing file (keeps the same fileId).

        Args:
            file_id: Drive ID of the file to overwrite.
            content: New file contents as bytes.
            mime_type: MIME type for the upload.
        """
        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type)
        self._service.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()

    # -- Misc ---------------------------------------------------------------

    @staticmethod
    def parse_modified_time(value: str | None) -> datetime | None:
        """Parse Drive's ISO 8601 ``modifiedTime`` to a naive UTC ``datetime``.

        Drive returns timestamps like ``"2026-05-07T12:34:56.789Z"``.

        Args:
            value: The string from a Drive API response, or ``None``.

        Returns:
            Naive UTC ``datetime``, or ``None`` if ``value`` was falsy.
        """
        if not value:
            return None
        # Strip trailing Z and fractional seconds for fromisoformat compatibility.
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.replace(tzinfo=None)

    def refresh_access_token(self) -> None:
        """Force-refresh the access token. Mostly useful for diagnostics.

        The underlying ``Credentials`` object refreshes lazily, so this is
        not needed in the normal request flow.
        """
        self._creds.refresh(GoogleAuthRequest())
