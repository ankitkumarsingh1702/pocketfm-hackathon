import { SUPERPOWERS } from '../config/constants'

/** Legend of Creator Superpowers; live ones get an accent dot, others are dimmed. */
export default function SuperpowersStrip() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
      {SUPERPOWERS.map((s) => (
        <span
          key={s.label}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
            fontWeight: 600,
            color: s.live ? 'var(--ink)' : 'var(--dim)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: s.live ? 'var(--accent)' : 'var(--grey-400)',
            }}
          />
          {s.label}
        </span>
      ))}
    </div>
  )
}
