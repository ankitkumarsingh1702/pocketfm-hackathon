// Shared data + pure helpers for the editable agent profiles in the AI Writers
// Room. Kept in a plain module (no component export) so both WritersRoom.jsx and
// AgentProfile.jsx can import the dropdown data and small helpers without
// tripping the react/only-export-components lint rule.

// ---- Dropdown data ---------------------------------------------------------

export const GENDERS = ['Female', 'Male', 'Non-binary']

export const CITIES = [
  'Mumbai', 'Delhi', 'Bengaluru', 'Hyderabad', 'Chennai', 'Kolkata', 'Pune',
  'Ahmedabad', 'Jaipur', 'Lucknow', 'Kanpur', 'Indore', 'Bhopal', 'Patna', 'Kochi',
]

export const GENRES = [
  'Thriller', 'Horror', 'Romance', 'Mythology', 'Crime', 'Comedy', 'Drama',
  'Historical', 'Sci-fi', 'Supernatural',
]

// A persona may select at most this many genres. Removing is always allowed.
export const MAX_GENRES = 4

// Shown on the temperature slider when a persona doesn't set its own value.
export const DEFAULT_TEMPERATURE = 0.9

// Fallback segment labels — used only if the audience roster fails to load.
export const DEFAULT_SEGMENTS = [
  'Gen-Z Thriller Fan',
  'Metro Binge-Watcher',
  'Small-Town Commuter',
  'Romance Devotee',
  'Mythology Traditionalist',
  'True-Crime Skeptic',
]

// Age band per segment, matched by a case-insensitive substring of the label.
// First matching rule wins; anything unmatched uses DEFAULT_AGE_BAND.
// NOTE: Age is now free-typed in the profile editor, so these bands no longer
// clamp or drive the age input. They are retained only for reference / reuse.
export const DEFAULT_AGE_BAND = [16, 70]

const AGE_BAND_RULES = [
  { needles: ['genz', 'gen-z'], band: [18, 27] },
  { needles: ['metro'], band: [22, 38] },
  { needles: ['commuter', 'small-town'], band: [24, 45] },
  { needles: ['romance'], band: [20, 40] },
  { needles: ['mytholog'], band: [35, 62] },
  { needles: ['crime', 'skeptic'], band: [28, 52] },
]

export function ageBandForSegment(segment) {
  const label = String(segment || '').toLowerCase()
  for (const rule of AGE_BAND_RULES) {
    if (rule.needles.some((needle) => label.includes(needle))) return rule.band
  }
  return DEFAULT_AGE_BAND
}

// ---- Small pure helpers ----------------------------------------------------

// Coerce to a whole number clamped into [min, max]; falls back to min.
export function clampAge(value, min, max) {
  const n = Number(value)
  if (!Number.isFinite(n)) return min
  return Math.max(min, Math.min(max, Math.round(n)))
}

// Effective temperature for display: the persona's own value, or the default.
export function effectiveTemp(agent) {
  return agent?.temperature ?? DEFAULT_TEMPERATURE
}

// Distinct, order-preserving segments from a loaded audience roster.
export function segmentOptions(audience) {
  const seen = []
  for (const a of audience || []) {
    if (a?.segment && !seen.includes(a.segment)) seen.push(a.segment)
  }
  return seen.length ? seen : DEFAULT_SEGMENTS
}

// Map a stored genre (often lowercase in the YAML rosters) to a display label:
// the canonical dropdown entry when it matches, otherwise a capitalised copy.
export function displayGenre(genre) {
  const canonical = GENRES.find((g) => g.toLowerCase() === String(genre).toLowerCase())
  if (canonical) return canonical
  const s = String(genre || '')
  return s ? s[0].toUpperCase() + s.slice(1) : s
}

// Genre membership + toggle are case-insensitive so existing lowercase genres
// are recognised; toggling on stores the canonical label and toggling off
// removes any case variant while preserving genres outside the dropdown.
export function hasGenre(genres, canonical) {
  return (genres || []).some((g) => g.toLowerCase() === canonical.toLowerCase())
}

export function toggleGenre(genres, canonical) {
  const list = genres || []
  if (hasGenre(list, canonical)) {
    return list.filter((g) => g.toLowerCase() !== canonical.toLowerCase())
  }
  // Cap additions at MAX_GENRES. Any pre-existing custom genres count toward the
  // cap and are preserved; when the cap is reached, adding is a no-op.
  if (list.length >= MAX_GENRES) return list
  return [...list, canonical]
}

// ---- Roster chip summaries -------------------------------------------------

// e.g. "28 · Female · Mumbai · Thriller, Horror"
export function audienceSummary(agent) {
  const parts = []
  if (agent.age != null) parts.push(String(agent.age))
  if (agent.gender) parts.push(agent.gender)
  if (agent.city) parts.push(agent.city)
  const genres = (agent.genres || []).slice(0, 2).map(displayGenre)
  if (genres.length) parts.push(genres.join(', '))
  return parts.join(' · ')
}

// e.g. "temp 0.9"
export function expertSummary(agent) {
  return `temp ${effectiveTemp(agent).toFixed(1)}`
}

// A defensive deep-ish copy so edits never mutate the fetched defaults.
export function cloneAgent(agent) {
  return { ...agent, genres: [...(agent.genres || [])], traits: [...(agent.traits || [])] }
}
