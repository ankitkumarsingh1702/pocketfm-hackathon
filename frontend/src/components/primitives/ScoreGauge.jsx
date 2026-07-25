import { useCountUp } from '../../hooks/useCountUp'
import { clamp } from '../../utils/format'

/** Circular 0–100 score gauge with an animated ring and count-up centre. */
export default function ScoreGauge({ score, size = 160, label = 'SCORE' }) {
  const stroke = 12
  const r = (size - stroke) / 2
  const circumference = 2 * Math.PI * r
  const target = clamp(score, 0, 100)

  const animScore = useCountUp(target, true, 900)
  const pct = animScore / 100

  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--grey-200)"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - pct)}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset var(--dur-slow) var(--ease-standard)' }}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontSize: size * 0.26,
            fontWeight: 600,
            color: 'var(--ink)',
            lineHeight: 1,
          }}
        >
          {animScore}
        </span>
        <span className="label-upper" style={{ marginTop: 4, fontSize: 10 }}>
          {label}
        </span>
      </div>
    </div>
  )
}
