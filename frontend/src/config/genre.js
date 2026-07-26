/**
 * Static configuration for the Genre Converter lens.
 *
 * Limits mirror the service (backend/story-genre-convertor/api.py) so the UI can
 * reject impossible input before spending a request, and the copy explaining a
 * rejection can be specific rather than echoing a 422.
 */

/** api.py MIN_CHARS — shorter than this has no plot to extract. */
export const MIN_CHARS = 400

/** api.py MAX_CHARS — past this a conversion runs the long-form lane instead. */
export const MAX_CHARS = 60000

/** api.py LONGFORM_MAX_CHARS — the long-form lane's own ceiling (~70k words). */
export const LONGFORM_MAX_CHARS = 400000

/**
 * How often to ask the service how a running job is doing.
 *
 * The rate is deliberately not constant, and deliberately not a backoff — it
 * tightens as the job approaches plausible completion. A conversion takes five
 * to eight minutes, so early on the answer is always "still running" and
 * polling hard buys nothing; near the end a finished scene should not sit
 * unreported. Each tier applies until `untilMs` of watching has elapsed:
 *
 *   first 3 minutes   every 20s
 *   minutes 3–5       every 10s
 *   after that        every 5s
 *
 * A poll is a cheap in-memory dict lookup on the service side, so the cost of
 * the faster phases is bounded and small.
 */
export const POLL_SCHEDULE = [
  { untilMs: 3 * 60 * 1000, intervalMs: 20 * 1000 },
  { untilMs: 5 * 60 * 1000, intervalMs: 10 * 1000 },
  { untilMs: Infinity, intervalMs: 5 * 1000 },
]

/**
 * Stop polling after this long. A short conversion is five to eight minutes;
 * twenty is well past "slow" and into "something is wrong". A long-form run
 * writes a chapter at a time and legitimately takes most of an hour.
 */
export const POLL_TIMEOUT_MS = 20 * 60 * 1000
export const LONGFORM_POLL_TIMEOUT_MS = 90 * 60 * 1000

/** Human labels for the job's `stage` field, across both lanes. */
export const STAGE_LABELS = {
  extract: 'Extracting the plot skeleton',
  transform: 'Writing the rewrite, scene by scene',
  cast: 'Casting the roles, once, up front',
  outline: 'Outlining the chapters',
  write: 'Writing, chapter by chapter',
  verify: 'Checking every beat against the page',
}

/** The stages a conversion moves through, in order, for the progress checklist. */
export const STAGE_ORDER = ['extract', 'transform', 'verify']

/** The long-form lane's stages: chapters, a fixed cast, and a story bible. */
export const LONGFORM_STAGE_ORDER = ['extract', 'cast', 'outline', 'write', 'verify']

/** Short forms of the same, for the checklist where space is tight. */
export const STAGE_SHORT = {
  extract: 'Extract',
  transform: 'Rewrite',
  cast: 'Cast',
  outline: 'Outline',
  write: 'Write',
  verify: 'Verify',
}

/** Human labels and explanations for the three fidelity components. */
export const RECALL_LABELS = {
  load_bearing_recall: {
    label: 'Load-bearing beats',
    hint: 'Pivots the story collapses without. Weighted heaviest.',
  },
  beat_recall: {
    label: 'All beats',
    hint: 'Every plot beat the source skeleton found.',
  },
  edge_recall: {
    label: 'Causal links',
    hint: 'Beat-causes-beat edges still legible in the rewrite.',
  },
}

/** Seed story, long enough to clear MIN_CHARS, so the lens is demoable cold. */
export const SAMPLE_SOURCE = `The reading room had been closed for eleven years, and Leo had the only key.

He came on Sundays, when the building was empty, and worked through the boxes one at a time. The provenance records were supposed to be a formality — a signature here, a date there, confirmation that the collection had arrived the way the catalogue said it had. By the fourth box he knew that it had not.

The signatures were all in the same hand. Not forged badly; forged patiently, over years, by someone who had all the time in the world and no reason to hurry. Leo sat with the folder open on his knees for a long time.

He took it to Ollerman on a Tuesday. The Head Curator listened without interrupting, which was worse than any interruption, and when Leo finished he said: "Yes. I wondered when someone would actually read them."

Leo had prepared for denial. He had not prepared for this.

"The collection was going to be broken up," Ollerman said. "Sold in pieces to four different countries. I made the paperwork say it had always been ours. It has been ours for thirty years now, and every scholar who has used it has used it because of what I did."

"That isn't yours to decide."

"No," Ollerman agreed. "It was not." He opened the desk drawer and took out a second folder, thicker than the first, and set it on the blotter between them. "I am retiring in March. The directorship is yours if you want it. The board will follow my recommendation."

He did not say what the second folder contained, and he did not need to.

Leo looked at it for a long moment, and then he picked up the first folder — his own — and walked out with it under his arm. He did not take the second.

By Friday the story was in the paper. By the following spring the collection had been broken up and sold, in pieces, to four different countries. Leo was not offered the directorship, and did not expect to be, and has never been quite sure, in the years since, whether he did the right thing.`
