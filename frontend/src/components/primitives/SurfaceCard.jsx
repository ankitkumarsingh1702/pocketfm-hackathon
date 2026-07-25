/** Padded surface container; `elevated` gives it the accent-bordered look. */
export default function SurfaceCard({ children, elevated = false, style }) {
  return (
    <div
      style={{
        background: elevated ? 'var(--surface-raised)' : 'var(--surface)',
        border: elevated ? '1.5px solid var(--accent)' : '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-6)',
        boxShadow: elevated ? 'var(--shadow-sm)' : 'none',
        ...style,
      }}
    >
      {children}
    </div>
  )
}
