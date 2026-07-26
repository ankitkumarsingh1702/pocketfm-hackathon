import { useCallback, useEffect, useRef, useState } from 'react'

import * as api from '../lib/api'

/**
 * Mood-First Search controller.
 *
 * Owns the whole feel-based discovery flow so the lens stays composition-only.
 * Two structural rules from the feature's design survive here, and both are
 * easy to break by accident:
 *
 *  1. `SearchResponse.mode` is NOT navigation. `empty | clarify | shelves |
 *     safety` are four states of ONE surface, held in `state.mode`. Routing them
 *     separately makes back-from-shelves land on the clarifying question, which
 *     reads as the app not having listened.
 *
 *  2. The target vector only moves through a slider drag or a clarify answer,
 *     both resolved server-side with no re-parse. Nothing here re-types the
 *     query, so refinement stays instant.
 */
export function useMoodSearch() {
  const [state, setState] = useState({ mode: 'empty', data: null })
  const [queryId, setQueryId] = useState(null)
  const [profileId, setProfileId] = useState(null)
  const [lastText, setLastText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // Which shelf is mid-refine, so only that shelf shows a pending state.
  const [refining, setRefining] = useState(null)

  // The opened doorway (episode list). Null = showing the search surface.
  const [playing, setPlaying] = useState(null)

  // Reference data, fetched once. `catalogReady` separates "still fetching" from
  // "this endpoint is not there" — without it a missing backend renders as a
  // permanent "Loading starters…", which reads as a hang rather than an outage.
  const [starters, setStarters] = useState([])
  const [sliders, setSliders] = useState([])
  const [profiles, setProfiles] = useState([])
  const [catalogReady, setCatalogReady] = useState(false)
  const [catalogError, setCatalogError] = useState(null)

  // Latest-wins guard: switching listener quickly fires overlapping searches,
  // and without this an older response can land last and win.
  const runIdRef = useRef(0)

  useEffect(() => {
    let alive = true
    // Starters decide the empty state, so its outcome is the one that settles
    // `catalogReady`. Sliders and profiles are enhancements — their absence
    // removes a control rather than breaking the surface.
    api
      .moodStarters()
      .then((d) => {
        if (!alive) return
        setStarters(d.starters || [])
        setCatalogError(null)
      })
      .catch((e) => {
        if (alive) setCatalogError(e.message || 'Mood catalog unavailable.')
      })
      .finally(() => {
        if (alive) setCatalogReady(true)
      })

    api.moodSliders().then((d) => alive && setSliders(d.sliders || [])).catch(() => {})
    api.moodProfiles().then((d) => alive && setProfiles(d.profiles || [])).catch(() => {})

    return () => {
      alive = false
    }
  }, [])

  const runSearch = useCallback(async (text, nextProfileId) => {
    const trimmed = (text || '').trim()
    if (!trimmed) return
    const runId = ++runIdRef.current
    setLoading(true)
    setError(null)
    try {
      const data = await api.moodSearch(trimmed, nextProfileId ?? null)
      if (runId !== runIdRef.current) return // superseded
      setQueryId(data.query_id)
      setState({ mode: data.mode, data })
      setPlaying(null)
    } catch (e) {
      if (runId !== runIdRef.current) return
      setError(e.message || 'Search failed.')
    } finally {
      if (runId === runIdRef.current) setLoading(false)
    }
  }, [])

  /** Search from the box, or from a tapped starter. */
  const search = useCallback(
    (text) => {
      setLastText(text)
      return runSearch(text, profileId)
    },
    [runSearch, profileId],
  )

  /**
   * Switching listener re-runs the SAME query instead of clearing the screen.
   * That side-by-side is the whole point — if picking a listener reset you to
   * the empty state there would be nothing to compare against.
   */
  const pickProfile = useCallback(
    (nextId) => {
      setProfileId(nextId)
      if (lastText) runSearch(lastText, nextId)
    },
    [runSearch, lastText],
  )

  /** Answer, or skip, the one clarifying question. */
  const answer = useCallback(
    async (optionId) => {
      if (!queryId) return
      setLoading(true)
      setError(null)
      try {
        const data = await api.moodClarify(queryId, optionId)
        setState({ mode: data.mode, data })
      } catch (e) {
        setError(e.message || 'Could not answer that.')
      } finally {
        setLoading(false)
      }
    },
    [queryId],
  )

  /**
   * Slider nudge. Replaces only the shelf that moved — re-rendering all three
   * makes a nudge look like a fresh search.
   */
  const refine = useCallback(
    async (shelf, sliderDeltas) => {
      if (!queryId) return
      setRefining(shelf.id)
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
      } catch (e) {
        // A failed nudge leaves the shelf exactly as it was; surface it quietly
        // rather than replacing results the listener is still reading.
        setError(e.message || 'Could not refine that shelf.')
      } finally {
        setRefining(null)
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
  }, [])

  const closeDoorway = useCallback(() => setPlaying(null), [])
  const dismissError = useCallback(() => setError(null), [])

  const reset = useCallback(() => {
    runIdRef.current += 1
    setState({ mode: 'empty', data: null })
    setQueryId(null)
    setLastText('')
    setPlaying(null)
    setError(null)
    setLoading(false)
  }, [])

  return {
    // surface state
    state,
    loading,
    error,
    refining,
    playing,
    queryId,
    lastText,
    // reference data
    starters,
    sliders,
    profiles,
    profileId,
    catalogReady,
    catalogError,
    // actions
    search,
    pickProfile,
    answer,
    refine,
    open,
    closeDoorway,
    dismissError,
    reset,
  }
}
