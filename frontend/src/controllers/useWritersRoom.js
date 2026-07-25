import { writersRoom } from '../lib/api'
import { toWritersRoomView } from '../utils/writersRoom'
import { useAsyncLens } from './useAsyncLens'

/**
 * Controller for the Writers Room lens.
 *
 * `run(story)` gathers the expert-critic panel's notes plus a consensus.
 *
 * @returns {{ data: object|null, loading: boolean, error: string|null, run: Function, reset: Function }}
 */
export function useWritersRoom() {
  return useAsyncLens(writersRoom, toWritersRoomView)
}
