/**
 * A stable, per-browser-session id used to tag the canon this session ingests.
 *
 * It lets the studio separate "your story" (what you added in this tab) from the
 * seeded demo canon (ANDHERA), so the Story Canon and DB / Memory tabs can scope
 * the graph to your own input and reset only that — never the demo. Backed by
 * sessionStorage so it survives a reload within the same tab but is fresh in a
 * new tab, which matches how a person thinks about "this session's story".
 */
const KEY = 'pocketfm.session_batch'

function makeId() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return `session-${crypto.randomUUID().slice(0, 8)}`
    }
  } catch {
    /* fall through to the Math.random path below */
  }
  return `session-${Math.random().toString(36).slice(2, 10)}`
}

function resolveBatch() {
  try {
    const existing = sessionStorage.getItem(KEY)
    if (existing) return existing
    const fresh = makeId()
    sessionStorage.setItem(KEY, fresh)
    return fresh
  } catch {
    // Private mode / storage disabled — a module-lifetime id is still stable
    // enough for the session.
    return makeId()
  }
}

/** The current session's canon batch tag (stable for the life of the tab). */
export const SESSION_BATCH = resolveBatch()
