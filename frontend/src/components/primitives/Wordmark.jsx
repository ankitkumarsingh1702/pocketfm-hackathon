/**
 * Brand lockup: the Pocket FM "Creators Superpower" logo mark + title/subtitle,
 * with an intro animation.
 *
 * The mark is a cropped, text-free version of the brand PNG (`/logo-mark.png`);
 * its white background blends into the header canvas. The mark renders a touch
 * larger than the type so the detailed icon stays legible at header sizes.
 */
export default function Wordmark({
  size = 20,
  title = 'Creator Superpower',
  subtitle = 'powered by amigoos',
}) {
  const markSize = Math.round(size * 1.45)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <img
        src="/logo-mark.png"
        width={markSize}
        height={markSize}
        alt="Pocket FM — Creators Superpower"
        style={{ display: 'block', flexShrink: 0, objectFit: 'contain' }}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, overflow: 'hidden' }}>
        <span
          className="pfm-rise"
          style={{
            fontFamily: 'var(--font-sans)',
            fontWeight: 650,
            fontSize: size * 0.85,
            letterSpacing: 'var(--tracking-tight)',
            lineHeight: 1.15,
            color: 'var(--ink)',
            display: 'inline-block',
            whiteSpace: 'nowrap',
          }}
        >
          {title}
        </span>
        {subtitle && (
          <span
            className="pfm-rise pfm-rise--late"
            style={{
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              fontSize: Math.max(11, size * 0.55),
              color: 'var(--muted)',
              display: 'inline-block',
              whiteSpace: 'nowrap',
            }}
          >
            {subtitle}
          </span>
        )}
      </div>
    </div>
  )
}
