import { useCallback, useMemo, useState } from 'react'

import { DEFAULT_STORY_META, SAMPLE_STORY } from '../config/constants'
import { isBlank, lastScene } from '../utils/story'
import { useAgentDirectory } from './useAgentDirectory'
import { useAudienceSimulator } from './useAudienceSimulator'
import { useCanon } from './useCanon'
import { useCliffhangerOptimizer } from './useCliffhangerOptimizer'
import { useDbMemory } from './useDbMemory'
import { useHealth } from './useHealth'
import { useWritersRoom } from './useWritersRoom'

/**
 * Top-level Simulated Studio controller.
 *
 * Owns the shared episode text and composes the lens controllers plus the
 * health probe. The active lens is no longer state here — the route decides
 * it, and the shell passes the matching lens id in as `activeTab`. `run()`
 * dispatches to whichever lens is active, shaping the request from the
 * current story. The shell that consumes this hook holds no logic of its own
 * — it only renders state and forwards callbacks.
 *
 * @param {string|null} activeTab lens id derived from the current route
 */
export function useStudio(activeTab) {
  const [story, setStory] = useState(SAMPLE_STORY)

  const health = useHealth()
  const audience = useAudienceSimulator()
  const cliffhanger = useCliffhangerOptimizer()
  const writersRoom = useWritersRoom()
  const canon = useCanon()
  const dbMemory = useDbMemory(activeTab === 'db')
  const agentDirectory = useAgentDirectory(activeTab === 'agents')

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
    agentDirectory,
    // orchestration
    run,
    isLoading: activeLoading,
    canRun: !isBlank(story) && !activeLoading,
  }
}
