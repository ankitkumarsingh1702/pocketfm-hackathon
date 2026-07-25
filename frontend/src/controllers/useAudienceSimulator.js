import { simulateAudience } from '../lib/api'
import { toAudienceView } from '../utils/audience'
import { useAsyncLens } from './useAsyncLens'

/**
 * Controller for the Audience Simulator lens.
 *
 * `run(story, n?)` fans a story out to the listener panel and exposes the
 * result as a ready-to-render view-model.
 *
 * @returns {{ data: object|null, loading: boolean, error: string|null, run: Function, reset: Function }}
 */
export function useAudienceSimulator() {
  return useAsyncLens(simulateAudience, toAudienceView)
}
