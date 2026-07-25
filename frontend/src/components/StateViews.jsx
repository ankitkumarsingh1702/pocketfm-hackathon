import { ProgressLine } from './primitives'

/** Loading state for a lens panel — indeterminate bar with a caption. */
export function LoadingState({ label }) {
  return (
    <div style={{ padding: '64px 0', maxWidth: 460, margin: '0 auto' }}>
      <ProgressLine label={label} />
    </div>
  )
}

/**
 * Error state for a lens panel; surfaces the backend message on the studio's
 * pale-red alert surface. Never colour alone — the glyph and the words carry
 * the state too.
 */
export function ErrorState({ message }) {
  return (
    <div
      role="alert"
      style={{
        marginTop: 40,
        padding: '16px 18px',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--accent-line)',
        background: 'var(--accent-soft)',
        fontSize: 14,
        lineHeight: 1.6,
        maxWidth: 620,
        display: 'flex',
        gap: 12,
        alignItems: 'flex-start',
      }}
    >
      <span aria-hidden="true" style={{ color: 'var(--accent-text-sm)', fontWeight: 700 }}>
        ✕
      </span>
      <span style={{ color: 'var(--ink)' }}>
        <strong style={{ color: 'var(--accent-text-sm)' }}>The run failed.</strong> {message}{' '}
        Check that the backend is reachable, then run it again.
      </span>
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
      <p style={{ margin: '0 auto', fontSize: 14, lineHeight: 1.6, maxWidth: '52ch' }}>{hint}</p>
    </div>
  )
}
