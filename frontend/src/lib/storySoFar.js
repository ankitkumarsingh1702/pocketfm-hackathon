/**
 * Assemble a bounded "story so far" recap from a show's prior episodes.
 *
 * The Audience Simulator posts one episode at a time. Without context, a listener
 * agent reacting to Episode 6 has no idea Episodes 1–5 happened — so swapping
 * episodes asks it to react to Ep 6 while clueless about Ep 5. This builds the
 * recap the reacting agents need, entirely from the bundled story data (the full
 * script of every prior episode is already in memory client-side).
 *
 * Recency-weighted: every prior episode contributes its title (the arc's shape,
 * so the agent knows those episodes happened and in what order), and the
 * immediately-preceding episode also contributes a short excerpt (what the
 * listener most recently heard). The result is hard-capped so a long season
 * never blows the prompt budget — the excerpt is dropped before the titles,
 * because knowing the arc matters more than the last episode's flavour.
 *
 * Returns '' for Episode 1 (nothing precedes it) or when there is no episode
 * data, so the caller simply omits the field and behaviour is unchanged.
 *
 * @param {{n:number,label?:string,title?:string,text?:string}[]} episodes
 * @param {number} episodeN  1-based number of the episode being posted
 * @param {{maxChars?:number,excerptChars?:number}} [opts]
 * @returns {string}
 */
export function buildStorySoFar(episodes, episodeN, opts = {}) {
  const maxChars = opts.maxChars ?? 1800
  const excerptChars = opts.excerptChars ?? 500

  if (!Array.isArray(episodes) || !episodeN || episodeN <= 1) return ''
  const prior = episodes.slice(0, episodeN - 1)
  if (prior.length === 0) return ''

  const titleLines = prior.map(
    (ep) => `Episode ${ep.n}: ${ep.title || ep.label || `Episode ${ep.n}`}`,
  )
  const titles = titleLines.join('\n')

  const last = prior[prior.length - 1]
  const excerpt = excerptOf(last?.text, excerptChars)
  const recap = excerpt
    ? `${titles}\n\nMost recently, in Episode ${last.n} (${last.title || last.label}):\n${excerpt}`
    : titles

  if (recap.length <= maxChars) return recap
  if (titles.length <= maxChars) return titles // drop the excerpt first
  return titles.slice(0, maxChars) // pathological episode count: hard trim
}

/** First ~`limit` chars of an episode script, cut on a clean sentence boundary. */
function excerptOf(text, limit) {
  if (!text) return ''
  const clean = text.trim()
  if (clean.length <= limit) return clean
  const cut = clean.slice(0, limit)
  const stop = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('\n'))
  return `${(stop > limit * 0.5 ? cut.slice(0, stop + 1) : cut).trim()}…`
}
