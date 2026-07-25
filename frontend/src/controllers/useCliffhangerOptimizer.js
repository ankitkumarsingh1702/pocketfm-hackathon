import { cliffhanger } from '../lib/api'
import { toCliffhangerView } from '../utils/cliffhanger'
import { useAsyncLens } from './useAsyncLens'

/**
 * Controller for the Cliffhanger Optimizer lens.
 *
 * `run(story, weakExcerpt)` rewrites a weak ending and A/B tests the hook lift.
 *
 * @returns {{ data: object|null, loading: boolean, error: string|null, run: Function, reset: Function }}
 */
export function useCliffhangerOptimizer() {
  return useAsyncLens(cliffhanger, toCliffhangerView)
}
