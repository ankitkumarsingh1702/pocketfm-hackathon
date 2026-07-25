/**
 * Static, app-wide configuration.
 *
 * Copy, catalogue entries, and default inputs live here so they can be changed
 * in one place without touching component or controller code.
 */

/** Lens tabs, in display order. `id` values key into the controllers. */
export const TABS = [
  { id: 'sim', label: 'Audience Simulator' },
  { id: 'opt', label: 'Cliffhanger Optimizer' },
  { id: 'room', label: 'Writers Room' },
  { id: 'canon', label: 'Story Canon' },
  { id: 'db', label: 'DB / Memory' },
  { id: 'genre', label: 'Genre Converter' },
]

export const DEFAULT_TAB = 'sim'

/**
 * Inner panels of the Story Canon tab, in display order. Each is one of the
 * four "real agent" capabilities layered on the knowledge graph.
 */
export const CANON_PANELS = [
  { id: 'graph', label: 'Canon Graph' },
  { id: 'holes', label: 'Plot Holes' },
  { id: 'planner', label: 'Cliffhanger Planner' },
  { id: 'agent', label: 'Showrunner Agent' },
  { id: 'mdp', label: 'MDP Optimizer' },
]

/**
 * The "Creator Superpowers" catalogue shown in the strip under the header.
 * `live` marks lenses that are actually wired to the backend today.
 */
export const SUPERPOWERS = [
  { label: 'Audience Simulator', live: true },
  { label: 'Cliffhanger Optimizer', live: true },
  { label: 'AI Writers Room', live: true },
  { label: 'Plot Hole Hunter', live: true },
  { label: 'Genre Converter', live: true },
  { label: 'AI Producer', live: false },
  { label: 'AI Rewrite Engine', live: false },
]

/** Simulated-listener panel size advertised in the header pill. */
export const AUDIENCE_ARMY = 1000

/** Scenes in the episode textarea are split on this delimiter. */
export const SCENE_DELIMITER = '---'

/** Seed story so the studio is demoable on first load. */
export const SAMPLE_STORY = `Scene 1: Meera arrives home late, the house unusually quiet.
---
Scene 2: A knock at the door. No one is there when she opens it.
---
Scene 3: She finds an old photograph tucked under her pillow.
---
Scene 4: The voice on the phone is her sister's — who died three years ago.`

/** Default title/episode sent with every simulation request. */
export const DEFAULT_STORY_META = {
  title: 'Untitled Episode',
  episode: 'Episode 1',
}

/** Human-readable labels for the backend's ordered drop-off stages. */
export const STAGE_LABELS = {
  hook: 'Hook',
  early: 'Early',
  middle: 'Middle',
  climax: 'Climax',
  cliffhanger: 'Cliffhanger',
  finished: 'Finished',
}
