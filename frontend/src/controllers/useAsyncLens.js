import { useCallback, useRef, useState } from 'react'

/**
 * Controller primitive shared by every lens hook.
 *
 * Owns the `{ data, loading, error }` lifecycle for a single async request,
 * runs the raw response through a pure `transform` into a view-model, and
 * guards against out-of-order responses (a slow earlier request can never
 * overwrite a newer one's result).
 *
 * @param {(...args: any[]) => Promise<any>} runner   service call to invoke
 * @param {(raw: any) => any} transform               pure response -> view-model
 */
export function useAsyncLens(runner, transform) {
  const [state, setState] = useState({ data: null, loading: false, error: null })
  const requestId = useRef(0)

  const run = useCallback(
    async (...args) => {
      const id = ++requestId.current
      setState((prev) => ({ ...prev, loading: true, error: null }))
      try {
        const raw = await runner(...args)
        if (id !== requestId.current) return // superseded by a newer run
        setState({ data: transform(raw), loading: false, error: null })
      } catch (err) {
        if (id !== requestId.current) return
        setState({ data: null, loading: false, error: err.message || 'Request failed' })
      }
    },
    [runner, transform],
  )

  const reset = useCallback(() => {
    requestId.current += 1 // invalidate any in-flight request
    setState({ data: null, loading: false, error: null })
  }, [])

  return { ...state, run, reset }
}
