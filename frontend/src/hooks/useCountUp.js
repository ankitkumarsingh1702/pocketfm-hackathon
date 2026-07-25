import { useEffect, useState } from 'react'

/**
 * Animate a number from 0 to `target` with an ease-out curve.
 *
 * Presentation-only animation logic, shared by metric readouts and the score
 * gauge so the easing stays consistent across the UI.
 *
 * @param {number} target   value to count up to
 * @param {boolean} active   when false, the value is pinned at 0
 * @param {number} duration  animation length in ms
 * @returns {number} the current animated value
 */
export function useCountUp(target, active = true, duration = 900) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    if (!active) {
      setValue(0)
      return undefined
    }

    let raf
    let start
    const step = (t) => {
      if (!start) start = t
      const progress = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(target * eased))
      if (progress < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)

    return () => cancelAnimationFrame(raf)
  }, [target, active, duration])

  return value
}
