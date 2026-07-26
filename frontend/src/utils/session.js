const STORAGE_KEY = 'pocketfm.session_batch'

function newBatchId() {
  const id =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `session-${id}`
}

function loadSessionBatch() {
  if (typeof window === 'undefined') return newBatchId()
  try {
    const existing = window.sessionStorage.getItem(STORAGE_KEY)
    if (existing) return existing
    const created = newBatchId()
    window.sessionStorage.setItem(STORAGE_KEY, created)
    return created
  } catch {
    return newBatchId()
  }
}

/** Stable for one browser tab; a new tab receives an isolated canon scope. */
export const SESSION_BATCH = loadSessionBatch()
