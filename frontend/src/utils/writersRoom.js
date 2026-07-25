/**
 * Transform a `WritersRoomResult` into the Writers Room view-model: one note
 * per expert persona plus the panel consensus.
 */

import { round } from './format'

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
