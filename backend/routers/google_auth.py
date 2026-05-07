"""OAuth 2.0 flow for connecting an enterprise's Google Drive.

Two endpoints implement the standard "authorization code with offline access"
flow used to obtain a long-lived refresh token:

1. ``GET  /auth/google/start``   — returns the Google consent URL to open.
2. ``GET  /auth/google/callback`` — Google redirects here with ``code`` and
   ``state`` (= the enterprise_id we passed in). We exchange the code for
   tokens and persist the refresh token in ``google_credentials``.

Helpers:

3. ``GET  /auth/google/status``  — for dev / debugging.
4. ``POST /auth/google/parent-folder`` — set the shared "Sprih" folder ID
   after the user has shared it with the agent's Google account.

The flow is intentionally minimal — auth on these endpoints uses the same
dev-mode bypass as the rest of the app. In production the start/callback
URLs would sit behind admin auth.
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from backend.config import settings
from backend.infra.google_drive import (
    DRIVE_SCOPES,
    GoogleDriveClient,
    credentials_from_refresh_token,
)
from backend.schemas.google_auth import (
    SetParentFolderRequest,
    StartAuthResponse,
    StatusResponse,
)
from backend.security.auth import EnterpriseContext, get_enterprise_context
from backend.services import drive_sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/google", tags=["google-auth"])


GOOGLE_AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


def _require_oauth_settings() -> None:
    """Raise 503 if the OAuth client isn't configured.

    The other Drive-aware code paths silently no-op when credentials are
    missing, but the auth endpoints can't function at all without an OAuth
    client, so we surface a clear error here.

    Raises:
        HTTPException 503: If client id/secret aren't set in settings.
    """
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth client not configured. Set "
                "SPRIH_GOOGLE_OAUTH_CLIENT_ID and "
                "SPRIH_GOOGLE_OAUTH_CLIENT_SECRET in .env and restart."
            ),
        )


@router.get("/start", response_model=StartAuthResponse)
async def start(
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
) -> StartAuthResponse:
    """Return the Google consent URL the operator should open in a browser.

    The ``state`` parameter carries the calling enterprise_id so the callback
    can persist the refresh token against the right tenant.

    Args:
        enterprise: Caller's enterprise context.

    Returns:
        ``StartAuthResponse`` with the authorize_url. Open it in a browser,
        sign in as the agent's Google account (e.g.
        ``sachchit.vekaria@sprih.com``), grant the Drive scope, and accept
        the redirect.
    """
    _require_oauth_settings()

    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(DRIVE_SCOPES),
        # access_type=offline + prompt=consent guarantees Google issues a
        # refresh_token even if the user has already granted the scope.
        "access_type": "offline",
        "prompt": "consent",
        "state": enterprise.enterprise_id,
        "include_granted_scopes": "true",
    }
    url = f"{GOOGLE_AUTHORIZE_ENDPOINT}?{urlencode(params)}"
    return StartAuthResponse(authorize_url=url, enterprise_id=enterprise.enterprise_id)


@router.get("/callback")
async def callback(request: Request) -> HTMLResponse:
    """Exchange the authorisation code for tokens and persist them.

    Google redirects here after the user grants consent. Query parameters:

    * ``code``  — short-lived authorisation code to exchange.
    * ``state`` — the enterprise_id we passed in ``/start``.
    * ``error`` — present only if the user denied or something went wrong.

    On success, persists the refresh token in ``google_credentials`` and
    renders a small confirmation HTML page so a human running through the
    flow in the browser sees something useful.

    Returns:
        An HTML response describing success (or the error from Google).

    Raises:
        HTTPException 400: If the callback is missing the ``code`` or
            ``state`` parameters, or the token exchange fails.
    """
    _require_oauth_settings()

    error = request.query_params.get("error")
    if error:
        return HTMLResponse(
            f"<h1>Google denied authorization</h1><p>{error}</p>",
            status_code=400,
        )

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state:
        raise HTTPException(
            status_code=400, detail="Missing 'code' or 'state' in callback"
        )

    # --- Exchange authorization code for tokens -----------------------------
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": settings.google_oauth_client_id,
                "client_secret": settings.google_oauth_client_secret,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    if resp.status_code != 200:
        logger.error("Google token exchange failed: %s %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=400, detail=f"Token exchange failed: {resp.text}"
        )

    payload = resp.json()
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    scope = payload.get("scope", " ".join(DRIVE_SCOPES))

    if not refresh_token:
        # Google omits refresh_token on subsequent grants unless prompt=consent
        # forces it. We always pass prompt=consent in /start so this is unusual.
        return HTMLResponse(
            "<h1>No refresh token returned</h1>"
            "<p>Google did not include a refresh token in its response — "
            "this happens if the app was previously authorized without "
            "prompt=consent. Revoke at "
            "<a href='https://myaccount.google.com/permissions'>"
            "myaccount.google.com/permissions</a> and try again.</p>",
            status_code=400,
        )

    # --- Look up the email this token belongs to ----------------------------
    creds = credentials_from_refresh_token(refresh_token, scopes=scope.split())
    creds.token = access_token  # avoid an immediate refresh round-trip
    client = GoogleDriveClient(creds)
    agent_email = client.get_email()

    # --- Persist -------------------------------------------------------------
    await drive_sync_service.store_credentials(
        enterprise_id=state,
        refresh_token=refresh_token,
        agent_email=agent_email,
        scopes=scope.split(),
        drive_parent_folder_id=None,  # set later via /parent-folder
    )

    return HTMLResponse(
        f"""
        <html><body style="font-family: sans-serif; max-width: 640px; margin: 4em auto;">
        <h1>Connected ✓</h1>
        <p>Stored a Drive refresh token for enterprise
            <code>{state}</code> as <code>{agent_email}</code>.</p>
        <p><strong>Next step:</strong> create the parent folder named
            <code>Sprih</code> in the user's Drive (or have the enterprise
            admin do this in their Drive), share it with
            <code>{agent_email}</code> as Editor, then call
            <code>POST /auth/google/parent-folder</code> with its folder ID.</p>
        </body></html>
        """,
    )


@router.get("/status", response_model=StatusResponse)
async def status(
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
) -> StatusResponse:
    """Return whether this enterprise has connected Drive and which folder.

    Args:
        enterprise: Caller's enterprise context.

    Returns:
        ``StatusResponse`` with ``connected``, ``agent_email`` and
        ``drive_parent_folder_id``.
    """
    s = await drive_sync_service.get_status(enterprise.enterprise_id)
    return StatusResponse(**s)


@router.post("/parent-folder", response_model=StatusResponse)
async def set_parent_folder(
    body: SetParentFolderRequest,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
) -> StatusResponse:
    """Record the shared "Sprih" parent folder ID for this enterprise.

    The enterprise admin (or, in test, ``write.to.sachchit@gmail.com``)
    creates a folder named ``Sprih`` in their Drive, shares it with the
    agent's Google account as Editor, and POSTs the folder ID here.

    Args:
        body: ``SetParentFolderRequest`` with the Drive folder ID.
        enterprise: Caller's enterprise context.

    Returns:
        Updated ``StatusResponse``.

    Raises:
        HTTPException 400: If the agent can't access the folder (e.g. it
            wasn't shared) or the folder doesn't exist.
        HTTPException 404: If the enterprise hasn't connected Drive yet.
    """
    # --- Verify the agent can actually see this folder before we persist ---
    import asyncio

    creds_row = await drive_sync_service._load_credentials(enterprise.enterprise_id)
    if creds_row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No Drive credentials for this enterprise. Run the OAuth "
                "flow at /auth/google/start first."
            ),
        )

    def _verify() -> None:
        client = drive_sync_service._build_client(creds_row)
        # If we can list the folder, we have access. Failure here means the
        # user hasn't shared the folder with the agent's account yet.
        client.list_files_recursive(body.drive_parent_folder_id)

    try:
        await asyncio.to_thread(_verify)
    except Exception as exc:
        logger.exception("Cannot access parent folder %s", body.drive_parent_folder_id)
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot access folder {body.drive_parent_folder_id}. "
                f"Make sure it has been shared with {creds_row.agent_email} "
                f"as Editor. ({type(exc).__name__}: {exc})"
            ),
        )

    ok = await drive_sync_service.set_parent_folder(
        enterprise.enterprise_id, body.drive_parent_folder_id
    )
    if not ok:
        raise HTTPException(
            status_code=404, detail="Credentials row missing — re-run /start."
        )

    s = await drive_sync_service.get_status(enterprise.enterprise_id)
    return StatusResponse(**s)
