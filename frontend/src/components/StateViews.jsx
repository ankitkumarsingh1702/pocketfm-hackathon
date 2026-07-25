import { ProgressLine } from './primitives'

/** Loading state for a lens panel — indeterminate bar with a caption. */
export function LoadingState({ label }) {
  return (
    <div style={{ padding: '64px 0', maxWidth: 460, margin: '0 auto' }}>
      <ProgressLine label={label} />
    </div>
  )
}

/** Error state for a lens panel; surfaces the backend message. */
export function ErrorState({ message }) {
  return (
    <div
      style={{
        marginTop: 40,
        padding: '16px 18px',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--danger)',
        background: 'var(--danger-bg)',
        color: 'var(--ink)',
        fontSize: 14,
        maxWidth: 620,
      }}
    >
      <strong>Simulation failed.</strong> {message}
    </div>
  )
}

/** Pre-run empty state prompting the user to run the lens. */
export function EmptyState({ title, hint }) {
  return (
    <div
      style={{
        marginTop: 40,
        padding: '48px 24px',
        border: '1px dashed var(--border)',
        borderRadius: 'var(--radius-lg)',
        textAlign: 'center',
        color: 'var(--muted)',
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', marginBottom: 6 }}>
        {title}
      </div>
      <p style={{ margin: 0, fontSize: 14 }}>{hint}</p>
    </div>
  )
}
