/**
 * Transform an `AudienceResult` (backend shape) into a flat view-model the
 * Audience Simulator tab can render directly.
 *
 * Keeping this here means the component never touches raw API fields, and the
 * mapping is unit-testable without mounting anything.
 */

import { STAGE_LABELS } from '../config/constants'
import { capitalize, fractionToPercent, round } from './format'

/** Prettify a backend stage id ("cliffhanger" -> "Cliffhanger"). */
function stageLabel(stage) {
  return STAGE_LABELS[stage] || capitalize(stage)
}

/**
 * Per-stage retention (share of listeners still tuned in), 0–100.
 * @returns {{label:string, value:number}[]}
 */
function toRetentionBars(result) {
  const stages = result.stages || []
  const curve = result.drop_off_curve || []
  return stages.map((stage, i) => ({
    label: stageLabel(stage),
    value: fractionToPercent(curve[i]),
  }))
}

/**
 * Per-stage drop-off (share of listeners lost entering each stage), 0–100.
 * Derived from the retention curve so the bar chart reads as "where people
 * leave" — the accent bar marks the worst stage.
 * @returns {{label:string, value:number}[]}
 */
function toDropOffBars(result) {
  const stages = result.stages || []
  const curve = result.drop_off_curve || []
  let prev = 1
  return stages.map((stage, i) => {
    const retained = Number(curve[i]) || 0
    const dropped = Math.max(0, prev - retained)
    prev = retained
    return { label: stageLabel(stage), value: fractionToPercent(dropped) }
  })
}

/** Map one raw `{ persona, reaction }` sample into a quote-card shape. */
function toReaction(sample) {
  const persona = sample?.persona || {}
  const reaction = sample?.reaction || {}
  const where = [persona.name, persona.city].filter(Boolean).join(' · ')
  return {
    quote: reaction.reason || '—',
    persona: where || persona.segment || 'Listener',
    emotion: reaction.emotion || null,
    hookScore: round(reaction.hook_score),
    willContinue: Boolean(reaction.will_continue),
  }
}

/** Map one `SegmentStat` into a display row. */
function toSegment(segment) {
  return {
    segment: segment.segment,
    count: segment.count,
    bingePct: round(segment.binge_pct),
    avgHook: round(segment.avg_hook),
  }
}

/**
 * @param {object} result raw AudienceResult from `POST /api/simulate/audience`
 * @returns {object|null} view-model, or null when there is no result
 */
export function toAudienceView(result) {
  if (!result) return null
  return {
    continueRate: round(result.binge_pct),
    avgHook: round(result.avg_hook_score),
    total: result.total || 0,
    retention: toRetentionBars(result),
    dropOff: toDropOffBars(result),
    reactions: (result.sample_reactions || []).map(toReaction),
    segments: (result.segments || []).map(toSegment),
    churnReasons: result.top_churn_reasons || [],
  }
}
