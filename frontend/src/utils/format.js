/**
 * Pure formatting + numeric helpers.
 *
 * No React, no side effects — safe to unit-test in isolation and to reuse from
 * both controllers (view-model building) and components (display).
 */

/** Clamp `n` into the inclusive `[min, max]` range. */
export function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n))
}

/** Round to the nearest integer, treating nullish/NaN as 0. */
export function round(n) {
  return Number.isFinite(n) ? Math.round(n) : 0
}

/** A 0–1 fraction as an integer percentage (0.734 -> 73). */
export function fractionToPercent(fraction) {
  return round((Number(fraction) || 0) * 100)
}

/** Format an integer with locale grouping (1000 -> "1,000"). */
export function formatInt(n) {
  return (Number(n) || 0).toLocaleString()
}

/** Prefix positive numbers with "+" for lift/delta display. */
export function signed(n) {
  const v = round(n)
  return v >= 0 ? `+${v}` : `${v}`
}

/** Capitalize the first character of a string. */
export function capitalize(s) {
  if (!s) return ''
  return s.charAt(0).toUpperCase() + s.slice(1)
}
