import { useEffect, useState } from 'react'

/**
 * Track whether the window has scrolled past a threshold.
 *
 * Drives the header's condense-to-pill transition. Two safeguards keep it from
 * flickering: **hysteresis** (separate on/off thresholds) so the flag can't
 * chatter when scrollY hovers at the boundary — including when the condensing
 * header changes its own height — and **rAF batching** so at most one update
 * runs per frame.
 *
 * @param {number} enter scrollY (px) at/above which the flag turns on
 * @param {number} exit  scrollY (px) below which it turns back off (must be <= enter)
 * @returns {boolean} true once past `enter`, until scrolled back under `exit`
 */
export function useScrolled(enter = 24, exit = Math.max(0, enter - 16)) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    let raf = 0
    const measure = () => {
      raf = 0
      const y = window.scrollY
      setScrolled((prev) => {
        if (!prev && y >= enter) return true
        if (prev && y <= exit) return false
        return prev // inside the hysteresis band — hold steady
      })
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(measure)
    }
    measure()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      if (raf) cancelAnimationFrame(raf)
    }
  }, [enter, exit])

  return scrolled
}
