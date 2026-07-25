import { useEffect, useRef } from 'react'

/**
 * Fire `handler(value)` whenever `value` transitions to a new truthy value.
 *
 * The bridge between controller state and toasts: watch an error string or a
 * result object, and the handler runs once per new occurrence — not on mount
 * (a state that already existed needs no re-announcing), not on re-renders,
 * and not when the value merely stays the same.
 */
export function useStatusToast(value, handler) {
  const prevRef = useRef(value)
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    const prev = prevRef.current
    prevRef.current = value
    if (value && value !== prev) handlerRef.current(value)
  }, [value])
}
