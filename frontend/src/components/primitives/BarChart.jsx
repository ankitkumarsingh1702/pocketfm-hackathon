import { useEffect, useState } from 'react'

/**
 * Horizontal bar chart. `data` is `[{ label, value }]` where `value` is a
 * percentage. The largest bar is highlighted in the accent colour; bars grow
 * in on mount / data change.
 */
export default function BarChart({ data }) {
  const max = Math.max(...data.map((d) => d.value), 1)
  const worstIdx = data.reduce((wi, d, i) => (d.value > data[wi].value ? i : wi), 0)

  const [grown, setGrown] = useState(false)
  useEffect(() => {
    setGrown(false)
    const raf = requestAnimationFrame(() =>
      requestAnimationFrame(() => setGrown(true)),
    )
    return () => cancelAnimationFrame(raf)
  }, [data])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {data.map((d, i) => (
        <div
          key={d.label}
          style={{
            display: 'grid',
            gridTemplateColumns: '120px 1fr 56px',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span className="label-upper" style={{ fontSize: 11, textAlign: 'right' }}>
            {d.label}
          </span>
          <div
            style={{
              background: 'var(--surface)',
              borderRadius: 4,
              height: 10,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: grown ? `${(d.value / max) * 100}%` : '0%',
                height: '100%',
                background: i === worstIdx ? 'var(--accent)' : 'var(--grey-400)',
                borderRadius: 4,
                transition: `width var(--dur-slow) var(--ease-standard) ${i * 80}ms`,
              }}
            />
          </div>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: i === worstIdx ? 'var(--accent-text-sm)' : 'var(--muted)',
              fontWeight: 600,
            }}
          >
            {d.value}%
          </span>
        </div>
      ))}
    </div>
  )
}
