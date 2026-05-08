/**
 * Per-thread Drive linkage client.
 *
 * Wraps the ``/threads/{tid}/mirror`` endpoints — see
 * ``backend/routers/mirror.py``. The edit thread panel uses these to
 * render a state-machine UI: not-linked / linked-healthy / linked-broken.
 */

import { ApiError, apiJson } from './client'

export interface MirrorStatus {
  linked: boolean
  provider?: string | null
  folder_id?: string | null
  folder_name?: string | null
  is_broken: boolean
}

export interface MirrorLinkResult {
  provider: string
  folder_id: string
  folder_name: string
}

/** Fetch current link state for a thread.
 *
 * On a linked thread the backend probes the provider for live folder
 * metadata so ``is_broken`` reflects "deleted in Drive" rather than
 * just "no mapping in our DB".
 */
export async function getMirrorStatus(threadId: string): Promise<MirrorStatus> {
  return apiJson<MirrorStatus>(`/threads/${threadId}/mirror`)
}

/**
 * Link (or re-link a broken mapping for) a thread to a Drive folder.
 *
 * @param folderName  The display name to use when creating the
 *                    provider-side folder. A new Drive folder is
 *                    created every time — duplicates by name are not
 *                    looked up.
 * @param ifBroken    Set when the user explicitly wants to re-link a
 *                    broken mapping. The backend rejects re-link
 *                    against a healthy folder regardless.
 */
export async function linkMirror(
  threadId: string,
  folderName: string,
  ifBroken = false,
): Promise<MirrorLinkResult> {
  try {
    return await apiJson<MirrorLinkResult>(`/threads/${threadId}/mirror`, {
      method: 'PUT',
      body: JSON.stringify({
        folder_name: folderName,
        if_broken: ifBroken,
      }),
    })
  } catch (e) {
    // Re-export the structured error so the UI can render the
    // ``detail`` string from a 409 / 412 verbatim.
    if (e instanceof ApiError) throw e
    throw e
  }
}

/** Drop the mapping. Provider folder is intentionally left in place. */
export async function unlinkMirror(threadId: string): Promise<void> {
  await apiJson<void>(`/threads/${threadId}/mirror`, { method: 'DELETE' })
}
