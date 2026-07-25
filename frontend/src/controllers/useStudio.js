import { useCallback, useMemo, useState } from 'react'

import {
  DEFAULT_STORY_META,
  DEFAULT_TAB,
  SAMPLE_STORY,
} from '../config/constants'
import { isBlank, lastScene } from '../utils/story'
import { useAudienceSimulator } from './useAudienceSimulator'
import { useCanon } from './useCanon'
import { useCliffhangerOptimizer } from './useCliffhangerOptimizer'
import { useDbMemory } from './useDbMemory'
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
  const canon = useCanon()
  const dbMemory = useDbMemory(activeTab === 'db')

  const lensByTab = useMemo(
    () => ({ sim: audience, opt: cliffhanger, room: writersRoom }),
    [audience, cliffhanger, writersRoom],
  )
  // Self-contained tabs (Writers Room, Story Canon) run their own controls, so
  // the shared run/loading state simply doesn't apply to them.
  const activeLens = lensByTab[activeTab]
  const activeLoading = activeLens ? activeLens.loading : false

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
    canon,
    dbMemory,
    // orchestration
    run,
    isLoading: activeLoading,
    canRun: !isBlank(story) && !activeLoading,
  }
}
