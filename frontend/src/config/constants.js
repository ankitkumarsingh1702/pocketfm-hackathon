/**
 * Static, app-wide configuration.
 *
 * Copy, catalogue entries, and default inputs live here so they can be changed
 * in one place without touching component or controller code.
 */

/**
 * The lenses, in display order. `id` values key into the controllers; `path`
 * is the lens's route, so every lens is a real URL that survives a reload.
 * `icon` names an entry in the `Icon` primitive; `title`/`blurb` feed the
 * page header.
 */
export const LENSES = [
  {
    id: 'sim',
    path: '/audience',
    label: 'Audience Simulator',
    icon: 'users',
    title: 'Audience Simulator',
    blurb:
      'Post an episode teaser and image; thousands of agentic listeners react live before release. Each one sees the image, remembers your past posts, and decides to scroll, like, share, or subscribe — edit a profile and its behaviour changes.',
  },
  {
    id: 'opt',
    path: '/cliffhanger',
    label: 'Cliffhanger Optimizer',
    icon: 'zap',
    title: 'Cliffhanger Optimizer',
    blurb:
      'Predicts the probability of binge-listening and rewrites your ending, then A/B tests the hook lift against the listener panel.',
  },
  {
    id: 'room',
    path: '/writers-room',
    label: 'Writers Room',
    icon: 'message',
    title: 'AI Writers Room',
    blurb: 'Your experts and your audience react to an episode — live, as each voice lands.',
  },
  {
    id: 'canon',
    path: '/canon',
    label: 'Story Canon',
    icon: 'book',
    title: 'Story Canon',
    blurb:
      'The shared knowledge graph every agent reads before it reacts — characters, clues, and plot threads remembered across episodes.',
  },
  {
    id: 'db',
    path: '/memory',
    label: 'DB / Memory',
    icon: 'database',
    title: 'DB / Memory',
    blurb:
      'Live proof the agents share one memory: every graph read and write, as it happens.',
  },
  {
    id: 'genre',
    path: '/genre',
    label: 'Genre Converter',
    icon: 'shuffle',
    title: 'Genre Converter',
    blurb:
      'Rewrite a story in another genre. The plot is extracted into a genre-neutral skeleton, rewritten scene by scene, then checked beat by beat against the page.',
  },
]

/** Where the studio lands on `/` or an unknown path. */
export const DEFAULT_LENS_PATH = '/audience'

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
 * Superpowers announced but not yet wired to the backend, listed in the
 * sidebar so the roadmap stays visible without pretending to be navigable.
 */
export const UPCOMING_SUPERPOWERS = ['AI Producer', 'AI Rewrite Engine']

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
