/** Indeterminate progress bar with a caption; drives lens loading states. */
export default function ProgressLine({ label, active = true }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div
        style={{
          height: 3,
          background: 'var(--grey-200)',
          borderRadius: 2,
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: 0,
            bottom: 0,
            width: '40%',
            background: 'var(--accent)',
            borderRadius: 2,
            animation: active ? 'pfm-progress 1.4s ease-in-out infinite' : 'none',
          }}
        />
      </div>
      <span className="label-upper" style={{ fontSize: 12 }}>
        {label}
      </span>
    </div>
  )
}
