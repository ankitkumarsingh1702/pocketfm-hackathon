/**
 * Progress bar with a caption; drives lens loading states.
 *
 * Indeterminate by default. Pass `value` (0-100) when the backend reports real
 * progress and the bar becomes determinate — which is worth doing wherever the
 * number exists, because a sweeping bar tells the user nothing about whether a
 * six-minute job is one minute in or five.
 */
export default function ProgressLine({ label, active = true, value }) {
  const determinate = typeof value === 'number' && Number.isFinite(value)
  const pct = determinate ? Math.max(0, Math.min(100, value)) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div
        role={determinate ? 'progressbar' : undefined}
        aria-valuenow={determinate ? pct : undefined}
        aria-valuemin={determinate ? 0 : undefined}
        aria-valuemax={determinate ? 100 : undefined}
        aria-label={determinate ? label : undefined}
        style={{
          height: 3,
          background: 'var(--grey-200)',
          borderRadius: 2,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={
            determinate
              ? {
                  height: '100%',
                  width: `${pct}%`,
                  background: 'var(--accent)',
                  borderRadius: 2,
                  transition: 'width var(--dur-med) var(--ease-standard)',
                }
              : {
                  position: 'absolute',
                  top: 0,
                  bottom: 0,
                  width: '40%',
                  background: 'var(--accent)',
                  borderRadius: 2,
                  animation: active ? 'pfm-progress 1.4s ease-in-out infinite' : 'none',
                }
          }
        />
      </div>
      <span className="label-upper" style={{ fontSize: 12 }}>
        {label}
      </span>
    </div>
  )
}
