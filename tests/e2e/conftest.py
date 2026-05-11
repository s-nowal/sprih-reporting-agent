"""E2E test fixtures — TestClient with real app lifespan, plus journey fixtures.

The client runs against the real FastAPI app with all infrastructure:
MariaDB, LocalStorage, and LangGraph agent service. Requires Docker
containers to be running (``docker compose up -d``).

Journey fixtures encode the state each ConOps subsection assumes its caller
is in. They compose: ``thread_with_history`` depends on ``fresh_thread``,
``mirrored_thread`` (future) would depend on ``thread_with_history``, and
so on. Each per-step test pulls only the fixture it needs. This keeps tests
independent (each can run in any order, in isolation, in parallel) while
still mirroring the user journey via fixture composition.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.testclient import TestClient

from backend.config import settings
from backend.infra.db import _get_url
from backend.main import app
from tests.utils.sse import parse_sse_events

ENTERPRISE_ID = "test-enterprise"


# =============================================================================
# Core fixtures — HTTP client, auth, DB session
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def seed_test_enterprise():
    """Ensure an ``enterprises`` row exists for the test tenant.

    Mirror-related tables FK to ``enterprises.enterprise_id``; without this
    row, inserts into ``mirror_credentials`` fail. Uses a sync pymysql
    connection so it doesn't spin up an asyncio loop at session-scope, which
    would conflict with the per-test async fixtures that follow.
    """
    import pymysql

    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT IGNORE INTO enterprises (enterprise_id, name) "
                "VALUES (%s, %s)",
                (ENTERPRISE_ID, "Test Enterprise"),
            )
        conn.commit()
    finally:
        conn.close()
    yield


@pytest.fixture(scope="session")
def client(seed_test_enterprise):
    """Session-scoped HTTP client backed by the real app.

    Uses Starlette's TestClient which triggers the ASGI lifespan:
    ``Registry.from_config``, ``set_registry``, ``init_agent_service`` on entry,
    ``teardown_registry`` on teardown.
    """
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Standard dev-mode auth headers for an authenticated request.

    Resolves to enterprise_id=``ENTERPRISE_ID`` server-side via
    ``SPRIH_AUTH_DEV_MODE``.
    """
    return {"x-enterprise-id": ENTERPRISE_ID}


@pytest.fixture
async def db_session():
    """Per-test async session bound to the test's own event loop.

    The app's session factory is created during the session-scoped lifespan
    and its connection pool is bound to that loop. Spinning up a fresh
    engine here keeps DB asserts isolated from the app's pool and avoids
    cross-loop errors. Use ``await db_session.rollback()`` between writes
    to release MySQL's REPEATABLE READ snapshot before re-reading.
    """
    engine = create_async_engine(_get_url(), pool_pre_ping=True)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        await engine.dispose()


# =============================================================================
# Journey fixtures — encode state from earlier ConOps subsections
# =============================================================================


@pytest.fixture
def fresh_thread(client, auth_headers):
    """A brand-new thread, just past ``POST /threads`` (ConOps §2.1 step 1).

    Mirrors the state Sara is in after she clicks into the plugin: an empty
    thread row exists, the S3 workspace is scaffolded, but no run has happened
    yet so the LangGraph checkpointer is empty and ``metadata['title']`` is
    unset.

    Yields:
        Dict with keys:
          - ``thread_id``: UUID of the newly-created thread.
          - ``workspace_root``: ``Path`` to the scaffolded S3 directory.
          - ``create_response``: full body of the POST /threads response.

    Cleanup: removes the workspace directory at the end of the test. DB rows
    are left in place — each fixture invocation gets a fresh UUID.
    """
    resp = client.post("/threads", json={}, headers=auth_headers)
    assert resp.status_code == 201, (
        f"fresh_thread setup failed: POST /threads returned "
        f"{resp.status_code}: {resp.text[:300]}"
    )
    create_response = resp.json()
    thread_id = create_response["thread_id"]
    workspace_root = Path(settings.storage_root) / (
        f"enterprise/{ENTERPRISE_ID}/workspaces/{thread_id}"
    )
    try:
        yield {
            "thread_id": thread_id,
            "workspace_root": workspace_root,
            "create_response": create_response,
        }
    finally:
        if workspace_root.exists():
            shutil.rmtree(workspace_root)


@pytest.fixture
def thread_with_history(client, auth_headers, fresh_thread):
    """A thread with one completed run (post ConOps §2.1 stream end).

    Composes on top of ``fresh_thread`` by driving the runs/stream call with
    a real first user message. After this fixture yields, the thread has:
      - ``threads.metadata['title']`` set (generated from the first message)
      - ``threads.status='idle'`` (run completed)
      - ``threads.values.messages`` populated with [user, assistant]
      - one ``jobs`` row with ``status='completed'``

    Use when the test needs Sara's post-first-run state but isn't testing
    §2.1 itself (e.g. §2.2 sidebar fetch, §2.3 thread reopen, §2.4 follow-up).

    Yields:
        Dict with everything from ``fresh_thread`` plus:
          - ``first_message``: the user message text that was sent.
          - ``run_events``: parsed SSE events from the runs/stream response.
    """
    thread_id = fresh_thread["thread_id"]
    first_message = (
        "In one short paragraph, name the GHG Protocol Scope 3 categories "
        "most relevant to a mid-size manufacturer."
    )
    resp = client.post(
        f"/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "reporting-agent",
            "input": {"messages": [{"type": "human", "content": first_message}]},
            "stream_mode": "values",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, (
        f"thread_with_history setup failed: runs/stream returned "
        f"{resp.status_code}: {resp.text[:300]}"
    )
    events = parse_sse_events(resp.text)
    assert events and events[-1]["event"] == "end", (
        f"thread_with_history expected SSE to end cleanly; got "
        f"{[e['event'] for e in events]}"
    )
    yield {
        **fresh_thread,
        "first_message": first_message,
        "run_events": events,
    }


# =============================================================================
# Mirror fixtures — real Google Drive
# =============================================================================
#
# These fixtures borrow the existing ``sprih`` enterprise's Drive refresh token
# and reuse it for the test enterprise so PUT /threads/{tid}/mirror hits a real
# Drive backend. Tests create real folders under sprih's configured parent and
# the teardown trashes them so the account stays tidy. The DB rows still land
# under ``test-enterprise`` so test data stays isolated from sprih.
#
# Requires: an existing mirror_credentials row for (sprih, google_drive) with
# a valid refresh_token and parent_folder_id.


@pytest.fixture
def real_mirror_credentials(seed_test_enterprise):
    """Copy sprih's google_drive credentials onto ``test-enterprise``.

    Reads the existing ``(sprih, google_drive)`` ``mirror_credentials`` row
    and upserts an equivalent row for ``test-enterprise`` so the test tenant
    has a working Drive provider. Removes the test row on teardown.

    Uses sync ``pymysql`` instead of the async engine because pytest-asyncio
    can teardown fixtures in a different event loop than the one that opened
    the connection pool, which produces cross-loop errors. A short
    synchronous round-trip avoids the issue entirely.

    Yields:
        Dict with the credential fields exposed to the test (``provider``,
        ``parent_folder_id``, ``agent_email``, ``refresh_token``, ``scopes``).
    """
    import pymysql

    def _connect() -> pymysql.connections.Connection:
        return pymysql.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name,
            cursorclass=pymysql.cursors.DictCursor,
        )

    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT enterprise_id, provider, agent_email, refresh_token, "
                "scopes, parent_folder_id, config "
                "FROM mirror_credentials "
                "WHERE enterprise_id = %s AND provider = %s",
                ("sprih", "google_drive"),
            )
            source = cur.fetchone()
            assert source is not None, (
                "real_mirror_credentials requires the (sprih, google_drive) "
                "row; run the OAuth flow in dev first."
            )
            cur.execute(
                "DELETE FROM mirror_credentials "
                "WHERE enterprise_id = %s AND provider = %s",
                (ENTERPRISE_ID, "google_drive"),
            )
            cur.execute(
                "INSERT INTO mirror_credentials "
                "(enterprise_id, provider, agent_email, refresh_token, "
                "scopes, parent_folder_id, config) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    ENTERPRISE_ID,
                    "google_drive",
                    source["agent_email"],
                    source["refresh_token"],
                    source["scopes"],
                    source["parent_folder_id"],
                    source["config"],
                ),
            )
        conn.commit()
        payload = {
            "provider": "google_drive",
            "parent_folder_id": source["parent_folder_id"],
            "agent_email": source["agent_email"],
            "refresh_token": source["refresh_token"],
            "scopes": source["scopes"],
        }
    finally:
        conn.close()

    try:
        yield payload
    finally:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM mirror_credentials "
                    "WHERE enterprise_id = %s AND provider = %s",
                    (ENTERPRISE_ID, "google_drive"),
                )
            conn.commit()
        finally:
            conn.close()


@pytest.fixture
def drive_cleanup(real_mirror_credentials):
    """Track Drive folder ids created during a test and trash them on teardown.

    Yields a ``track(folder_id, thread_id=...)`` callable. Teardown trashes
    every tracked folder via the Drive API (which also trashes everything
    inside) and clears the corresponding ``thread_mirror_mappings`` rows.
    Both teardown steps are synchronous so they don't interact with
    pytest-asyncio's loop lifecycle.
    """
    import pymysql

    from backend.infra.google_drive import (
        GoogleDriveClient,
        credentials_from_refresh_token,
    )

    captured_folders: list[str] = []
    captured_threads: list[str] = []

    def track(folder_id: str, *, thread_id: str | None = None) -> None:
        captured_folders.append(folder_id)
        if thread_id:
            captured_threads.append(thread_id)

    try:
        yield track
    finally:
        # Trash the Drive folders (move to bin — same call the user makes
        # when they delete a folder; safe because Drive keeps it for 30 days).
        if captured_folders:
            try:
                creds = credentials_from_refresh_token(
                    real_mirror_credentials["refresh_token"],
                    scopes=real_mirror_credentials["scopes"].split(),
                )
                client = GoogleDriveClient(creds)
                for fid in captured_folders:
                    try:
                        client._service.files().update(
                            fileId=fid,
                            body={"trashed": True},
                            supportsAllDrives=True,
                        ).execute()
                    except Exception as e:
                        print(f"drive_cleanup: failed to trash {fid}: {e}")
            except Exception as e:
                print(f"drive_cleanup: client setup failed: {e}")

        # Delete thread_mirror_mappings rows so subsequent tests start clean.
        if captured_threads:
            conn = pymysql.connect(
                host=settings.db_host,
                port=settings.db_port,
                user=settings.db_user,
                password=settings.db_password,
                database=settings.db_name,
            )
            try:
                with conn.cursor() as cur:
                    placeholders = ",".join(["%s"] * len(captured_threads))
                    cur.execute(
                        f"DELETE FROM thread_mirror_mappings "
                        f"WHERE thread_id IN ({placeholders})",
                        tuple(captured_threads),
                    )
                conn.commit()
            finally:
                conn.close()
