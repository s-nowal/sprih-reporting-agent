"""E2E test for ConOps §2.5 — Upload a file to the thread.

Spec source: ``docs/ConOps.md`` §2.5.

Drives ``POST /threads/{tid}/files`` with a multipart upload and verifies
the bytes land at the S3 input prefix the next run reads from.

Spec recap:

    Trigger: Sara drags a file into the composer.

    API call:
      - POST /threads/{thread_id}/files
        body: multipart/form-data with the file bytes

    Writes:
      S3 — file bytes at
        enterprise/{enterprise_id}/workspaces/{thread_id}/input/userUpload/{filename}

Requires:
  - Docker containers running (``docker compose up -d``)
"""

from __future__ import annotations


async def test_section_2_5_upload_file_to_thread(
    client, auth_headers, fresh_thread
):
    """Upload a file and assert it lands at the input/userUpload prefix."""
    thread_id = fresh_thread["thread_id"]
    workspace_root = fresh_thread["workspace_root"]

    filename = "acme_top50_suppliers_q3.csv"
    payload = (
        b"supplier_id,name,country,annual_spend_usd\n"
        b"S001,SteelCo,DE,1250000\n"
        b"S002,Polymerix,US,980030\n"
        b"S003,LogiTrans,IN,640000\n"
    )

    # =========================================================================
    # API call: multipart upload
    # =========================================================================
    resp = client.post(
        f"/threads/{thread_id}/files",
        files={"files": (filename, payload, "text/csv")},
        headers=auth_headers,
    )
    assert resp.status_code == 201, (
        f"POST /files returned {resp.status_code}: {resp.text[:300]}"
    )
    results = resp.json()
    assert isinstance(results, list) and len(results) == 1, (
        f"Spec: response should be a list of WriteResult, one per file; "
        f"got {results!r}"
    )
    write_result = results[0]
    # API returns the thread-relative path; the full storage key includes the
    # enterprise/workspace prefix and is verified below by reading the file
    # from disk.
    expected_rel_key = f"input/userUpload/{filename}"
    assert write_result.get("key") == expected_rel_key, (
        f"Spec: response should carry the thread-relative key "
        f"{expected_rel_key!r}; got {write_result.get('key')!r}"
    )
    assert write_result.get("size") == len(payload), (
        f"Spec: size in response should match uploaded bytes; "
        f"got {write_result.get('size')} vs {len(payload)}"
    )

    # =========================================================================
    # S3 write: bytes land at the path the next run reads from
    # =========================================================================
    uploaded = workspace_root / "input" / "userUpload" / filename
    assert uploaded.exists(), (
        f"Spec: file bytes should be persisted at {uploaded}"
    )
    assert uploaded.read_bytes() == payload, (
        "Spec: persisted bytes should match the uploaded payload exactly"
    )
