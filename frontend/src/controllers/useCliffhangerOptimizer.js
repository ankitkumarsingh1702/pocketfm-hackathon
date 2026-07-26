import { useEffect } from 'react'

import { cliffhanger } from '../lib/api'
import { toCliffhangerView } from '../utils/cliffhanger'
import { useAsyncLens } from './useAsyncLens'
import { useCliffhangerNarration } from './useCliffhangerNarration'

/**
 * Controller for the Cliffhanger Optimizer lens.
 *
 * `run(story, weakExcerpt)` rewrites a weak ending and A/B tests the hook lift.
 * The `narration` sub-controller voices both endings on demand so the lift is
 * *audible* (flat original vs dramatic optimized). It is folded into the returned
 * object so the existing `{...studio.cliffhanger}` spread carries it to the view
 * with no shell wiring.
 *
 * @returns {{ data: object|null, loading: boolean, error: string|null, run: Function, reset: Function, narration: object }}
 */
export function useCliffhangerOptimizer() {
  const lens = useAsyncLens(cliffhanger, toCliffhangerView)
  const narration = useCliffhangerNarration()

  // A fresh optimize invalidates any prior narration, so stale audio can never
  // play against new text. `reset` is stable, so this only fires when the ending
  // text actually changes — narration itself is produced only on an explicit click.
  const { reset: resetNarration } = narration
  const original = lens.data?.original
  const rewrite = lens.data?.rewrite
  useEffect(() => {
    resetNarration()
  }, [original, rewrite, resetNarration])

  return { ...lens, narration }
}
