/**
 * Compact backend-status indicator.
 *
 * Pure view of the `useHealth` controller's output: a coloured dot plus the
 * active provider/project when online, or a connecting/offline label.
 */
export default function HealthBadge({ online, info, error, loading }) {
  const color = online ? 'var(--success)' : error ? 'var(--danger)' : 'var(--warning)'

  let text
  if (online) {
    text = [info.provider, info.project, info.location].filter(Boolean).join(' · ')
    if (info.firestore) text += ' · Firestore'
  } else if (loading) {
    text = 'connecting…'
  } else {
    text = 'backend offline'
  }

  return (
    <span
      title={online ? 'Backend online' : error || 'Checking backend…'}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        fontSize: 12,
        fontFamily: 'var(--font-mono)',
        color: 'var(--muted)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-pill)',
        padding: '6px 12px',
        background: 'var(--surface)',
        whiteSpace: 'nowrap',
        maxWidth: 320,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: color,
          boxShadow: `0 0 8px ${color}`,
          flexShrink: 0,
        }}
      />
      {text}
    </span>
  )
}
