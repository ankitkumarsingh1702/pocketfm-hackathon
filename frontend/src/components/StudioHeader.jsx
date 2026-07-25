import { AUDIENCE_ARMY } from '../config/constants'
import { formatInt } from '../utils/format'
import { useScrolled } from '../hooks/useScrolled'
import { Pill, Wordmark } from './primitives'
import HealthBadge from './HealthBadge'

/**
 * Sticky studio header: accent rule + wordmark, backend health, and the
 * audience-army pill. Condenses into a floating glass pill once scrolled.
 * Scroll-driven styling is local presentation state (via `useScrolled`); the
 * `health` data is supplied by the controller.
 */
export default function StudioHeader({ health }) {
  // Wide hysteresis band (condense at 48px, expand under 8px) so the header
  // can't oscillate near the threshold as it changes its own height.
  const scrolled = useScrolled(48, 8)

  return (
    <>
      <div
        style={{
          height: 3,
          background: 'var(--accent)',
          position: 'sticky',
          top: 0,
          zIndex: 60,
        }}
      />
      <div
        style={{
          position: 'sticky',
          top: 3,
          zIndex: 50,
          display: 'flex',
          justifyContent: 'center',
          padding: scrolled ? '12px 0' : '0',
          transition: 'padding 320ms var(--ease-standard)',
        }}
      >
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 24,
            width: scrolled ? 'min(860px,94%)' : '100%',
            maxWidth: scrolled ? 860 : 'none',
            margin: '0 auto',
            padding: scrolled ? '10px 28px' : '28px clamp(20px,4vw,56px) 20px',
            borderRadius: scrolled ? 'var(--radius-pill)' : 0,
            // Interpolatable start/end values (0-alpha colour, blur(0)) so the
            // glass effect fades in/out smoothly instead of hard-switching —
            // `transparent`/`none` can't be transitioned.
            backgroundColor: scrolled ? 'rgba(255,255,255,0.72)' : 'rgba(255,255,255,0)',
            border: scrolled ? '1px solid rgba(230,230,230,0.9)' : '1px solid transparent',
            boxShadow: scrolled ? '0 10px 30px rgba(14,14,14,0.12)' : '0 10px 30px rgba(14,14,14,0)',
            backdropFilter: scrolled ? 'blur(20px) saturate(180%)' : 'blur(0px) saturate(100%)',
            WebkitBackdropFilter: scrolled ? 'blur(20px) saturate(180%)' : 'blur(0px) saturate(100%)',
            boxSizing: 'border-box',
            // Own compositor layer — stops the backdrop-filter repaint flicker
            // Chromium shows on a sticky element while scrolling.
            transform: 'translateZ(0)',
            // Transition only what changes (never `all`, which animates layout
            // every frame and drags backdrop-filter through non-interpolatable
            // states).
            transition: [
              'width var(--dur-med) var(--ease-standard)',
              'max-width var(--dur-med) var(--ease-standard)',
              'padding var(--dur-med) var(--ease-standard)',
              'border-radius var(--dur-med) var(--ease-standard)',
              'background-color var(--dur-med) var(--ease-standard)',
              'border-color var(--dur-med) var(--ease-standard)',
              'box-shadow var(--dur-med) var(--ease-standard)',
            ].join(', '),
          }}
        >
          <Wordmark size={scrolled ? 18 : 24} />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
            <HealthBadge {...health} />
            <Pill label="Superpower Army =" value={formatInt(AUDIENCE_ARMY)} tone="accent" />
          </div>
        </header>
      </div>
    </>
  )
}
