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
          style={{
            fontFamily: 'var(--font-sans)',
            fontWeight: 800,
            fontSize: size * 0.85,
            letterSpacing: '-0.01em',
            color: 'var(--ink)',
            textTransform: 'uppercase',
            display: 'inline-block',
            animation: 'pfm-wordmark-in 600ms ease both',
          }}
        >
          {title}
        </span>
        {subtitle && (
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 600,
              fontSize: Math.max(12, size * 0.42),
              letterSpacing: '0.06em',
              color: 'var(--ink)',
              opacity: 0.55,
              display: 'inline-block',
              animation: 'pfm-wordmark-in 600ms ease 120ms both',
            }}
          >
            {subtitle}
          </span>
        )}
      </div>
    </div>
  )
}
