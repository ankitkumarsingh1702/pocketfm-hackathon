/**
 * Turn a base64 audio payload from the backend into a playable object URL.
 *
 * Lives here (not in the fetch client) so the caller owns the URL lifecycle:
 * create the URL when a clip arrives, and revoke it when the clip is replaced or
 * the view unmounts. Object URLs must be revoked or they leak across demo runs.
 *
 * @param {string} base64  raw base64 audio (no data: prefix)
 * @param {string} mime    e.g. "audio/mp3" (Chirp) or "audio/wav" (Gemini)
 * @returns {string|null}  an object URL, or null when there is nothing to play
 */
export function audioUrlFromBase64(base64, mime = 'audio/wav') {
  if (!base64) return null
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return URL.createObjectURL(new Blob([bytes], { type: mime }))
}

/** Release an object URL created by {@link audioUrlFromBase64}. Safe on null. */
export function revokeAudioUrl(url) {
  if (url) URL.revokeObjectURL(url)
}
