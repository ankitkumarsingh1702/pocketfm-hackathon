import { useEffect, useState } from 'react'
import { health } from '../lib/api'

/**
 * Controller for the backend health probe.
 *
 * Fetches `/health` once on mount and exposes a small status object the
 * `HealthBadge` renders. Never throws — connection failures surface as `error`.
 *
 * @returns {{ info: object|null, error: string|null, loading: boolean, online: boolean }}
 */
export function useHealth() {
  const [state, setState] = useState({ info: null, error: null, loading: true })

  useEffect(() => {
    let alive = true
    health()
      .then((info) => alive && setState({ info, error: null, loading: false }))
      .catch((err) => alive && setState({ info: null, error: err.message, loading: false }))
    return () => {
      alive = false
    }
  }, [])

  return { ...state, online: Boolean(state.info) }
}
