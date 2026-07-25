/** Large tabular-figures metric readout (hero / lg / md sizes). */
export default function MetricNumber({
  value,
  size = 'hero',
  tone = 'accent',
  suffix = '',
}) {
  const sizes = { hero: 'var(--text-display)', lg: 48, md: 28 }
  const color =
    tone === 'accent' ? 'var(--accent)' : tone === 'ink' ? 'var(--ink)' : 'var(--muted)'
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        fontFeatureSettings: '"tnum" 1',
        fontSize: sizes[size],
        fontWeight: 600,
        lineHeight: 1,
        letterSpacing: '-0.02em',
        color,
      }}
    >
      {value}
      {suffix}
    </span>
  )
}
