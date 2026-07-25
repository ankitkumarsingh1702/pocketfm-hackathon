/**
 * Transform a `CliffhangerResult` into the Cliffhanger Optimizer view-model:
 * the original ending, its rewrite, the before/after hook scores, and the lift.
 */

import { round } from './format'

/**
 * @param {object} result raw CliffhangerResult from `POST /api/lenses/cliffhanger`
 * @returns {object|null} view-model, or null when there is no result
 */
export function toCliffhangerView(result) {
  if (!result) return null
  const before = round(result.before_score)
  const after = round(result.after_score)
  return {
    original: result.original || '',
    rewrite: result.rewrite || '',
    before,
    after,
    lift: round(result.lift ?? after - before),
    rationale: result.rationale || '',
    improved: after >= before,
  }
}
