import { useCallback, useMemo, useRef, useState } from 'react'

import { ToastContext } from './toast-context'

/**
 * App-wide toast notifications.
 *
 * `useToast()` returns `{ success(message), error(message) }`. Toasts stack
 * bottom-right (bottom of the screen on mobile), auto-dismiss — errors linger
 * longer than successes — and can be dismissed by hand. The stack is capped
 * and an identical message never shows twice at once, so a polling loop that
 * keeps failing reads as one calm notice, not a cascade.
 *
 * Announcement: the viewport is a polite live region; each error also carries
 * `role="alert"`. State is never colour alone — tone comes with a glyph and
 * the words themselves.
 */

const MAX_STACK = 4
const TTL_MS = { success: 5000, error: 8000 }

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const idRef = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (tone, message) => {
      setToasts((current) => {
        if (current.some((t) => t.tone === tone && t.message === message)) return current
        const id = ++idRef.current
        setTimeout(() => dismiss(id), TTL_MS[tone] ?? 5000)
        return [...current.slice(-(MAX_STACK - 1)), { id, tone, message }]
      })
    },
    [dismiss],
  )

  const api = useMemo(
    () => ({
      success: (message) => push('success', message),
      error: (message) => push('error', message),
    }),
    [push],
  )

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toasts" aria-live="polite" aria-label="Notifications">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast toast--${t.tone}`}
            role={t.tone === 'error' ? 'alert' : 'status'}
          >
            <span className="toast__glyph" aria-hidden="true">
              {t.tone === 'error' ? '✕' : '✓'}
            </span>
            <span className="toast__msg">{t.message}</span>
            <button
              type="button"
              className="toast__close"
              onClick={() => dismiss(t.id)}
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
