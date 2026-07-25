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
import { useWritersRoom } from './useWritersRoom'

/**
 * Top-level Simulated Studio controller.
 *
 * Owns the shared inputs (episode text, active lens tab) and composes the three
 * lens controllers plus the health probe. Its `run()` dispatches to whichever
 * lens is active, shaping the request from the current story. The page that
 * consumes this hook holds no logic of its own — it only renders state and
 * forwards callbacks.
 */
export function useStudio() {
  const [activeTab, setActiveTab] = useState(DEFAULT_TAB)
  const [story, setStory] = useState(SAMPLE_STORY)

  const health = useHealth()
  const audience = useAudienceSimulator()
  const cliffhanger = useCliffhangerOptimizer()
  const writersRoom = useWritersRoom()

  const lensByTab = useMemo(
    () => ({ sim: audience, opt: cliffhanger, room: writersRoom }),
    [audience, cliffhanger, writersRoom],
  )
  const activeLens = lensByTab[activeTab]

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
      case 'room':
        writersRoom.run(payload)
        break
      default:
        break
    }
  }, [activeTab, story, buildStory, audience, cliffhanger, writersRoom])

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
    writersRoom,
    // orchestration
    run,
    isLoading: activeLens.loading,
    canRun: !isBlank(story) && !activeLens.loading,
  }
}
