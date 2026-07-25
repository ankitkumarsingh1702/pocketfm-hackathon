import { useContext } from 'react'

import { ToastContext } from './toast-context'

/** `{ success(message), error(message) }` — see ToastProvider. */
export function useToast() {
  return useContext(ToastContext)
}
