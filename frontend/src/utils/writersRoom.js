/**
 * Transform a `WritersRoomResult` into the Writers Room view-model: one note
 * per expert persona plus the panel consensus.
 */

import { round } from './format'

// Weights for the graded "still following" retention read. Kept in lockstep with
// the backend (app/lenses/writers_room.py) so the live tally and the final
// verdict converge on the same number. A raw will_continue count can only be 0%
// or 100%; blending in the hook score keeps a weak episode from collapsing to a
// flat, broken-looking 0%.
export const RETENTION_INTENT_WEIGHT = 0.7
export const RETENTION_ENGAGEMENT_WEIGHT = 0.3

/**
 * One listener's graded likelihood of staying with the story, in 0..1.
 * @param {{ will_continue?: boolean, hook_score?: number }} reaction
 */
export function retentionScore(reaction) {
  const intent = reaction?.will_continue ? 1 : 0
  const hook = Number(reaction?.hook_score)
  const engagement = Number.isFinite(hook) ? Math.max(0, Math.min(1, hook / 100)) : 0
  return RETENTION_INTENT_WEIGHT * intent + RETENTION_ENGAGEMENT_WEIGHT * engagement
}

/** Map one `ExpertFeedback` entry into a display note. */
function toNote(feedback) {
  const note = feedback?.note || {}
  return {
    role: feedback.role || 'Expert',
    persona: feedback.persona || '',
    verdict: note.verdict || 'mixed',
    score: round(note.score),
    strengths: note.strengths || [],
    issues: note.issues || [],
    fix: note.fix_suggestion || '',
  }
}

/**
 * @param {object} result raw WritersRoomResult from `POST /api/lenses/writers-room`
 * @returns {object|null} view-model, or null when there is no result
 */
export function toWritersRoomView(result) {
  if (!result) return null
  return {
    notes: (result.panel || []).map(toNote),
    consensus: result.consensus || '',
  }
}
