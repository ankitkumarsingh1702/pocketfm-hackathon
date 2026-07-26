import { useCallback, useEffect, useRef, useState } from 'react'

import { getAudienceFacets, getAudienceMember, getAudienceMembers, reactAgent } from '../lib/api'

/**
 * Agent Directory — audience-population controller.
 *
 * Owns the search/filter/pagination state for the 1000s of persisted listener
 * agents and fetches them server-side (search + filters + a page of results at a
 * time), so the directory stays fast at scale. Also loads the filter facets once
 * and, on demand, one agent's full profile + memory/history for the detail view.
 *
 * Non-`q` filters fire immediately; the free-text query is debounced. A
 * monotonic request token guards against out-of-order responses.
 */

export const PAGE_SIZE = 48

export const AGE_BANDS = {
  '13-17': { ageMin: 13, ageMax: 17 },
  '18-24': { ageMin: 18, ageMax: 24 },
  '25-34': { ageMin: 25, ageMax: 34 },
  '35-44': { ageMin: 35, ageMax: 44 },
  '45-54': { ageMin: 45, ageMax: 54 },
  '55+': { ageMin: 55, ageMax: null },
}
export const AGE_BAND_OPTIONS = Object.keys(AGE_BANDS)

const EMPTY = { q: '', segment: '', city: '', gender: '', genres: [], ageBand: '', hasMemory: null }

export function useAudiencePopulation(active = true) {
  const [filters, setFilters] = useState(EMPTY)
  const [debouncedQ, setDebouncedQ] = useState('')
  const [members, setMembers] = useState([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(null)
  const [facets, setFacets] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState({ loading: false, data: null, error: null })
  const [liveReaction, setLiveReaction] = useState({ loading: false, data: null, error: null })
  const tokenRef = useRef(0)

  // Debounce the free-text query only (300ms); dropdowns/chips fire immediately.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(filters.q.trim()), 300)
    return () => clearTimeout(t)
  }, [filters.q])

  // Filter facets: load once when the directory becomes active.
  useEffect(() => {
    if (!active || facets) return undefined
    let alive = true
    getAudienceFacets()
      .then((f) => alive && setFacets(f))
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [active, facets])

  const band = AGE_BANDS[filters.ageBand] || {}
  const ageMin = band.ageMin ?? null
  const ageMax = band.ageMax ?? null

  // Fetch a page whenever the active filters or the offset change.
  useEffect(() => {
    if (!active) return undefined
    let cancelled = false
    const id = ++tokenRef.current
    setLoading(true)
    setError(null)
    getAudienceMembers({
      q: debouncedQ,
      segment: filters.segment,
      city: filters.city,
      gender: filters.gender,
      genres: filters.genres,
      ageMin,
      ageMax,
      hasMemory: filters.hasMemory,
      limit: PAGE_SIZE,
      offset,
    })
      .then((res) => {
        if (cancelled || id !== tokenRef.current) return
        setMembers(res.members || [])
        setTotal(res.total || 0)
        setLoading(false)
        setLoaded(true)
      })
      .catch((err) => {
        if (cancelled || id !== tokenRef.current) return
        setError(err.message || 'Failed to load agents')
        setLoading(false)
        setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [
    active,
    debouncedQ,
    filters.segment,
    filters.city,
    filters.gender,
    filters.hasMemory,
    filters.genres,
    ageMin,
    ageMax,
    offset,
  ])

  // Any filter change resets to the first page.
  const setFilter = useCallback((patch) => {
    setOffset(0)
    setFilters((f) => ({ ...f, ...patch }))
  }, [])

  const toggleGenre = useCallback((g) => {
    setOffset(0)
    setFilters((f) => ({
      ...f,
      genres: f.genres.includes(g) ? f.genres.filter((x) => x !== g) : [...f.genres, g],
    }))
  }, [])

  const resetFilters = useCallback(() => {
    setOffset(0)
    setFilters(EMPTY)
  }, [])

  const fetchDetail = useCallback(async (id) => {
    setDetail({ loading: true, data: null, error: null })
    try {
      const data = await getAudienceMember(id)
      setDetail({ loading: false, data, error: null })
    } catch (err) {
      setDetail({ loading: false, data: null, error: err.message || 'Failed to load this agent' })
    }
  }, [])

  const openMember = useCallback(
    (id) => {
      setSelectedId(id)
      setLiveReaction({ loading: false, data: null, error: null })
      fetchDetail(id)
    },
    [fetchDetail],
  )

  const closeMember = useCallback(() => {
    setSelectedId(null)
    setDetail({ loading: false, data: null, error: null })
    setLiveReaction({ loading: false, data: null, error: null })
  }, [])

  // Talk to the currently-open agent: it reacts live and (on success) its memory
  // is re-read so the history visibly grows.
  const askAgent = useCallback(
    async (teaser) => {
      const text = String(teaser || '').trim()
      if (!selectedId || !text) return
      setLiveReaction({ loading: true, data: null, error: null })
      try {
        const data = await reactAgent(selectedId, { text })
        setLiveReaction({ loading: false, data, error: null })
        fetchDetail(selectedId)
      } catch (err) {
        setLiveReaction({ loading: false, data: null, error: err.message || 'Reaction failed' })
      }
    },
    [selectedId, fetchDetail],
  )

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const page = Math.floor(offset / PAGE_SIZE)
  const nextPage = useCallback(
    () => setOffset((o) => (o + PAGE_SIZE < total ? o + PAGE_SIZE : o)),
    [total],
  )
  const prevPage = useCallback(() => setOffset((o) => Math.max(0, o - PAGE_SIZE)), [])

  const activeFilterCount =
    (debouncedQ ? 1 : 0) +
    (filters.segment ? 1 : 0) +
    (filters.city ? 1 : 0) +
    (filters.gender ? 1 : 0) +
    (filters.ageBand ? 1 : 0) +
    (filters.hasMemory != null ? 1 : 0) +
    (filters.genres.length ? 1 : 0)

  return {
    filters,
    setFilter,
    toggleGenre,
    resetFilters,
    members,
    total,
    loading,
    loaded,
    error,
    facets,
    offset,
    page,
    pageCount,
    pageSize: PAGE_SIZE,
    nextPage,
    prevPage,
    selectedId,
    detail,
    openMember,
    closeMember,
    liveReaction,
    askAgent,
    activeFilterCount,
  }
}
