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
    id: "agents",
    path: "/agents",
    label: "Agent Directory",
    icon: "grid",
    title: "Agent Directory",
    blurb:
      "Every agent in the studio in one place — what each one does, the tools it runs, and the shared memory it reads and writes, updating live as they work.",
  },
  {
    id: "sim",
    path: "/audience",
    label: "Audience Simulator",
    icon: "users",
    title: "Audience Simulator",
    blurb:
      "A panel of simulated listeners reacts to your episode before a single real one hears it — continue-rate, drop-off, and reactions by segment.",
      'Post an episode teaser and image; thousands of agentic listeners react live before release. Each one sees the image, remembers your past posts, and decides to scroll, like, share, or subscribe — edit a profile and its behaviour changes.',
  },
  // {
  //   id: "opt",
  //   path: "/cliffhanger",
  //   label: "Cliffhanger Optimizer",
  //   icon: "zap",
  //   title: "Cliffhanger Optimizer",
  //   blurb:
  //     "Predicts the probability of binge-listening and rewrites your ending, then A/B tests the hook lift against the listener panel.",
  // },
  {
    id: "room",
    path: "/writers-room",
    label: "Writers Room",
    icon: "message",
    title: "AI Writers Room",
    blurb:
      "Your experts and your audience react to an episode — live, as each voice lands.",
  },
  {
    id: "genre",
    path: "/genre",
    label: "Story Rewrite Engine",
    icon: "shuffle",
    title: "Story Rewrite Engine",
    blurb:
      "Rewrite a story in another genre. The plot is extracted into a genre-neutral skeleton, rewritten scene by scene, then checked beat by beat against the page.",
  },
  {
    id: "mood",
    path: "/mood",
    label: "Mood Search",
    icon: "heart",
    title: "Mood-First Search",
    blurb:
      "Listeners search by how they want to feel, not by genre. An ambiguous feeling comes back as three readings side by side, each pointing at the arc that delivers it — never a 200-episode series.",
  },
  {
    id: "canon",
    path: "/canon",
    label: "Story Canon",
    icon: "book",
    title: "Story Canon",
    blurb:
      "The shared knowledge graph every agent reads before it reacts — characters, clues, and plot threads remembered across episodes.",
  },
  {
    id: "db",
    path: "/memory",
    label: "DB / Memory",
    icon: "database",
    title: "DB / Memory",
    blurb:
      "Live proof the agents share one memory: every graph read and write, as it happens.",
  },
];

/** Where the studio lands on `/` or an unknown path. */
export const DEFAULT_LENS_PATH = "/audience";

/**
 * The reasoning agents that make up the studio — the roster shown in the Agent
 * Directory, in display order. This is descriptive metadata (what each agent
 * does, the method it runs, and which shared memory it touches); the live
 * numbers and recent activity are hydrated at runtime from the canon graph and
 * the shared-memory activity log.
 *
 * `source` MUST match the string each agent tags its reads/writes with in the
 * backend activity log (`record_activity(..., source=...)`), so the directory
 * can join each profile to its real memory activity. `route` is where the agent
 * runs; `panel` names its inner tab when it lives inside Story Canon.
 */
export const AGENTS = [
  {
    id: "agent",
    name: "Showrunner Agent",
    source: "Showrunner",
    route: "/canon",
    panel: "agent",
    role: "Runs the whole episode loop — ingest, continuity, simulate, decide, fix, re-simulate — until it converges.",
    methods: ["State-graph agent", "Knowledge graph", "LLM"],
    memory:
      "Writes new canon on ingest, reads the graph to reason, and writes its decision back.",
    reads: true,
    writes: true,
  },
  {
    id: "holes",
    name: "Plot Hole Hunter",
    source: "Plot Hole Hunter",
    route: "/canon",
    panel: "holes",
    role: "Scans one episode against the whole show canon for contradictions, timeline slips and dangling clues.",
    methods: ["Contradiction traversal", "Knowledge graph", "LLM"],
    memory:
      "Traverses every fact, conflict and unpaid clue in shared memory before it ranks issues.",
    reads: true,
    writes: false,
  },
  {
    id: "planner",
    name: "Cliffhanger Planner",
    source: "Cliffhanger Planner",
    route: "/canon",
    panel: "planner",
    role: "Searches a tree of possible endings to find the cliffhanger with the strongest hook lift.",
    methods: ["Tree / beam search", "Knowledge graph", "LLM"],
    memory:
      "Reads the canon subgraph so every candidate ending stays true to the story.",
    reads: true,
    writes: false,
  },
  {
    id: "mdp",
    name: "MDP Optimizer",
    source: "MDP Optimizer",
    route: "/canon",
    panel: "mdp",
    role: "Treats the ending as a decision process and searches a policy for the highest expected reward.",
    methods: ["MDP policy search", "Knowledge graph", "LLM"],
    memory:
      "Reads canon to score each policy state against what the audience already knows.",
    reads: true,
    writes: false,
  },
  {
    id: "room",
    name: "Writers' Room",
    source: "Writers' Room",
    route: "/writers-room",
    panel: null,
    role: "A panel of expert personas debates the episode and returns a single, grounded verdict.",
    methods: ["Multi-agent debate", "Knowledge graph", "LLM"],
    memory:
      "Reads canon for context, then writes the room's verdict back to the log.",
    reads: true,
    writes: true,
  },
  {
    id: "sim",
    name: "Audience Simulator",
    source: "Audience",
    route: "/audience",
    panel: null,
    role: "Fans a few archetypes into a representative panel and predicts drop-off and retention.",
    methods: ["Persona fan-out", "Knowledge graph", "LLM"],
    memory:
      "Reads canon, then writes each segment's verdict back as edges on the episode.",
    reads: true,
    writes: true,
  },
  {
    id: "opt",
    name: "Cliffhanger Optimizer",
    source: "Cliffhanger",
    route: "/cliffhanger",
    panel: null,
    role: "Rewrites a weak ending into a sharper cliffhanger, then A/B-tests the hook lift.",
    methods: ["Knowledge graph", "LLM"],
    memory: "Reads canon so the rewrite never breaks continuity.",
    reads: true,
    writes: false,
  },
  {
    id: "canon",
    name: "Story Canon",
    source: "Canon Ingest",
    route: "/canon",
    panel: "graph",
    role: "The shared brain: extracts characters, relationships and atomic facts from every episode.",
    methods: ["Entity + fact extraction", "Knowledge graph"],
    memory:
      "Builds and holds the knowledge graph every other agent reads from and writes to.",
    reads: false,
    writes: true,
    hub: true,
  },
];

/** LLM model each persona tier runs on (Gemini provider — see backend config). */
export const PERSONA_MODEL = {
  audience: "gemini-2.5-flash",
  expert: "gemini-2.5-pro",
};

/**
 * Inner panels of the Story Canon tab, in display order. Each is one of the
 * four "real agent" capabilities layered on the knowledge graph.
 */
export const CANON_PANELS = [
  { id: "graph", label: "Canon Graph" },
  { id: "holes", label: "Plot Holes" },
  { id: "planner", label: "Cliffhanger Planner" },
  { id: "agent", label: "Showrunner Agent" },
  { id: "mdp", label: "MDP Optimizer" },
];

/**
 * Superpowers announced but not yet wired to the backend, listed in the
 * sidebar so the roadmap stays visible without pretending to be navigable.
 */
export const SUPERPOWERS = [
  { label: "Audience Simulator", live: true },
  { label: "Cliffhanger Optimizer", live: true },
  { label: "AI Writers Room", live: true },
  { label: "Plot Hole Hunter", live: true },
  // { label: "AI Producer", live: false },
  // { label: "AI Rewrite Engine", live: false },
];

/**
 * Superpowers named in the sidebar but not yet wired to a backend, so the
 * roadmap stays visible without pretending to be navigable.
 */
// export const UPCOMING_SUPERPOWERS = ["AI Producer", "AI Rewrite Engine"];

/** Simulated-listener panel size advertised in the header pill. */
export const AUDIENCE_ARMY = 1000;

/** Scenes in the episode textarea are split on this delimiter. */
export const SCENE_DELIMITER = "---";

/** Seed story so the studio is demoable on first load. */
export const SAMPLE_STORY = `Scene 1: Meera arrives home late, the house unusually quiet.
---
Scene 2: A knock at the door. No one is there when she opens it.
---
Scene 3: She finds an old photograph tucked under her pillow.
---
Scene 4: The voice on the phone is her sister's — who died three years ago.`;

/** Default title/episode sent with every simulation request. */
export const DEFAULT_STORY_META = {
  title: "Untitled Episode",
  episode: "Episode 1",
};

/** Human-readable labels for the backend's ordered drop-off stages. */
export const STAGE_LABELS = {
  hook: "Hook",
  early: "Early",
  middle: "Middle",
  climax: "Climax",
  cliffhanger: "Cliffhanger",
  finished: "Finished",
};
