import { useCallback, useMemo, useState } from 'react'

import {
  DEFAULT_STORY_META,
  DEFAULT_TAB,
  SAMPLE_STORY,
} from '../config/constants'
import { isBlank, lastScene } from '../utils/story'
import { useAudienceSimulator } from './useAudienceSimulator'
import { useCliffhangerOptimizer } from './useCliffhangerOptimizer'
import { useHealth } from './useHealth'

/**
 * Top-level Simulated Studio controller.
 *
 * Owns the shared inputs (episode text, active lens tab) and composes the two
 * shared-input lens controllers plus the health probe. Its `run()` dispatches to
 * whichever of those lenses is active, shaping the request from the current
 * story. The Writers Room lens is self-contained (see `WritersRoom.jsx`) and is
 * not driven from here. The page that consumes this hook holds no logic of its
 * own — it only renders state and forwards callbacks.
 */
export function useStudio() {
  const [activeTab, setActiveTab] = useState(DEFAULT_TAB)
  const [story, setStory] = useState(SAMPLE_STORY)

  const health = useHealth()
  const audience = useAudienceSimulator()
  const cliffhanger = useCliffhangerOptimizer()

  // The Writers Room lens is self-contained (its own composer, streaming run,
  // and editable rosters live in `WritersRoom.jsx`), so it is intentionally not
  // wired into the shared story input / Run control here. Only the lenses that
  // consume the shared input appear in this map.
  const lensByTab = useMemo(
    () => ({ sim: audience, opt: cliffhanger }),
    [audience, cliffhanger],
  )
  // Falls back to the audience lens for loading/canRun bookkeeping when the
  // active tab (e.g. the Writers Room) drives its own run lifecycle.
  const activeLens = lensByTab[activeTab] ?? audience

  /** Assemble the request `story` object from the current inputs. */
  const buildStory = useCallback(
    () => ({ ...DEFAULT_STORY_META, text: story }),
    [story],
  )

  /** Run the currently-active lens against the current story. */
  const run = useCallback(() => {
    if (isBlank(story)) return
    const payload = buildStory()
    switch (activeTab) {
      case 'sim':
        audience.run(payload)
        break
      case 'opt':
        cliffhanger.run(payload, lastScene(story))
        break
      default:
        break
    }
  }, [activeTab, story, buildStory, audience, cliffhanger])

  return {
    // shared inputs
    activeTab,
    setActiveTab,
    story,
    setStory,
    // backend status
    health,
    // per-lens state
    audience,
    cliffhanger,
    // orchestration
    run,
    isLoading: activeLens.loading,
    canRun: !isBlank(story) && !activeLens.loading,
  }
}
