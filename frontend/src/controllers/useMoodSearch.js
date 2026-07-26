import { useCallback, useEffect, useState } from 'react'

import * as api from '../lib/api'

/**
 * Mood-First Search controller.
 *
 * Owns the whole feel-based discovery flow so the view stays presentational.
 * Two structural rules from the feature's PRD survive here:
 *
 *  1. `SearchResponse.mode` is NOT navigation. `empty | clarify | shelves |
 *     safety` are four states of ONE surface — they live in `state.mode`, never
 *     in separate routes, so backing out of shelves never lands on the question.
 *
 *  2. The target vector only moves via slider refine / clarify answers, both of
 *     which resolve server-side with no re-parse. The view never re-types.
 */
export function useMoodSearch() {
  // The feel surface and its four modes.
  const [state, setState] = useState({ mode: 'empty', data: null })
  const [queryId, setQueryId] = useState(null)
  const [profileId, setProfileId] = useState(null)
  const [lastText, setLastText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Internal view: the feel surface, an opened doorway, or the dev-only Lab.
  const [view, setView] = useState('feel')
  const [playing, setPlaying] = useState(null)

  // Reference data, fetched once.
  const [starters, setStarters] = useState([])
  const [sliders, setSliders] = useState([])
  const [profiles, setProfiles] = useState([])

  // The Lab (genre baseline + retrieval trace) is a demo artifact, not a
  // feature — reachable only at ?dev, exactly as the PRD requires.
  const [devMode, setDevMode] = useState(false)

  useEffect(() => {
    setDevMode(new URLSearchParams(window.location.search).has('dev'))
    api.moodStarters().then((d) => setStarters(d.starters || [])).catch(() => {})
    api.moodSliders().then((d) => setSliders(d.sliders || [])).catch(() => {})
    api.moodProfiles().then((d) => setProfiles(d.profiles || [])).catch(() => {})
  }, [])

  const runSearch = useCallback(async (text, nextProfileId) => {
    const trimmed = (text || '').trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    try {
      const data = await api.moodSearch(trimmed, nextProfileId ?? null)
      setQueryId(data.query_id)
      setState({ mode: data.mode, data })
      setView('feel')
    } catch (e) {
      setError(e.message || 'Search failed.')
    } finally {
      setLoading(false)
    }
  }, [])

  /** Empty-state search / starter tap. */
  const search = useCallback(
    (text) => {
      setLastText(text)
      return runSearch(text, profileId)
    },
    [runSearch, profileId],
  )

  /**
   * Switching listener re-runs the SAME query rather than clearing the screen —
   * that side-by-side is the entire "watch the ranking move" demo beat.
   */
  const pickProfile = useCallback(
    (nextId) => {
      setProfileId(nextId)
      if (lastText) runSearch(lastText, nextId)
    },
    [runSearch, lastText],
  )

  /** Answer (or skip) the one clarifying question. */
  const answer = useCallback(
    async (optionId) => {
      if (!queryId) return
      setLoading(true)
      setError(null)
      try {
        const data = await api.moodClarify(queryId, optionId)
        setState({ mode: data.mode, data })
      } catch (e) {
        setError(e.message || 'Could not answer.')
      } finally {
        setLoading(false)
      }
    },
    [queryId],
  )

  /** Slider nudge — replaces only the shelf that moved so it doesn't read as a
   *  fresh search. No LLM in this path. */
  const refine = useCallback(
    async (shelf, sliderDeltas) => {
      if (!queryId) return
      try {
        const data = await api.moodRefine(
          queryId,
          shelf.id,
          shelf.target_axes,
          sliderDeltas,
        )
        const moved = data.shelves && data.shelves[0]
        if (!moved) return
        setState((prev) => ({
          mode: 'shelves',
          data: {
            ...prev.data,
            shelves: prev.data.shelves.map((s) => (s.id === shelf.id ? moved : s)),
          },
        }))
      } catch {
        // A failed nudge should leave the current shelf exactly as it was.
      }
    },
    [queryId],
  )

  /** Card tap -> open the doorway (episode window starting at the entry point). */
  const open = useCallback((card) => {
    setPlaying({
      seriesId: card.series_id,
      seriesTitle: card.series_title,
      entryEpisode: card.entry_episode,
      entryLabel: card.entry_label,
    })
    setView('playing')
  }, [])

  const backToFeel = useCallback(() => setView('feel'), [])
  const openLab = useCallback(() => setView('lab'), [])

  return {
    // surface state
    state,
    loading,
    error,
    view,
    playing,
    queryId,
    lastText,
    // reference data
    starters,
    sliders,
    profiles,
    profileId,
    devMode,
    // actions
    search,
    pickProfile,
    answer,
    refine,
    open,
    backToFeel,
    openLab,
  }
}
