import { useEffect, useId, useRef, useState } from 'react'

/**
 * Renders a mermaid definition as an inline SVG.
 *
 * LAZY BY DESIGN. Mermaid is a couple of megabytes — an order of magnitude more
 * than the rest of the app — and only one surface uses it. The dynamic import
 * keeps it out of the main bundle so every other lens still loads at the same
 * speed, and the chunk is served from our own origin, so an offline demo works.
 *
 * THEMED FROM THE LIVE TOKENS. Mermaid needs concrete colour values, not CSS
 * variables, because it derives further shades from them. Rather than duplicate
 * the palette here, the values are read off the document at render time — so
 * changing a token in index.css moves the diagram too, and there is no second
 * palette to keep in sync.
 *
 * NEVER A BLANK BOX. A mermaid syntax error normally renders nothing, or worse,
 * a red error graphic. Since this is shown to an audience, a failure falls back
 * to the definition as readable source with the parser's complaint above it:
 * degraded, still explainable, never a hole in the page.
 */

/** Read a CSS custom property off the root element. */
function token(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

let mermaidPromise = null

/** Load and configure mermaid exactly once per page. */
function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(({ default: mermaid }) => {
      const ink = token('--ink', '#111111')
      const muted = token('--muted', '#626262')
      const canvas = token('--canvas', '#ffffff')
      const surface = token('--surface', '#f6f6f6')
      const border = token('--border', '#e6e6e6')
      const accent = token('--accent', '#e96b6b')
      const accentSoft = token('--accent-soft', '#fdecec')
      const accentLine = token('--accent-line', '#f4b8b8')
      const font = token('--font-sans', 'system-ui, sans-serif')

      mermaid.initialize({
        startOnLoad: false,
        // `strict` sanitises label HTML. The diagrams here are authored by us,
        // but this surface is the one place we inject a string into an SVG
        // renderer, so it stays locked down.
        securityLevel: 'strict',
        theme: 'base',
        fontFamily: font,
        flowchart: { curve: 'basis', nodeSpacing: 40, rankSpacing: 46, padding: 12 },
        themeVariables: {
          background: canvas,
          primaryColor: surface,
          primaryTextColor: ink,
          primaryBorderColor: border,
          secondaryColor: accentSoft,
          secondaryBorderColor: accentLine,
          tertiaryColor: canvas,
          tertiaryBorderColor: border,
          lineColor: muted,
          textColor: ink,
          mainBkg: surface,
          nodeBorder: border,
          clusterBkg: canvas,
          clusterBorder: border,
          edgeLabelBackground: canvas,
          titleColor: ink,
          fontSize: '13px',
          // Red is the supporting accent, never the primary hierarchy.
          errorBkgColor: accentSoft,
          errorTextColor: ink,
          nodeTextColor: ink,
          accentColor: accent,
        },
      })
      return mermaid
    })
  }
  return mermaidPromise
}

export default function MermaidDiagram({ definition, label = 'Diagram', zoom = 1 }) {
  // `useId` gives a stable, unique target id. Mermaid requires one per render
  // and rejects ids that start with a digit, so the colons React emits are
  // stripped rather than passed through.
  const rawId = useId()
  const domId = `mmd-${rawId.replace(/[^a-zA-Z0-9_-]/g, '')}`

  const [svg, setSvg] = useState('')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    setLoading(true)
    setError(null)

    loadMermaid()
      .then((mermaid) => mermaid.render(domId, definition))
      .then(({ svg: out }) => {
        if (!alive.current) return
        setSvg(out)
        setLoading(false)
      })
      .catch((e) => {
        if (!alive.current) return
        setError(e?.message || String(e))
        setLoading(false)
        // Mermaid leaves its measurement node behind when a parse throws.
        document.getElementById(domId)?.remove()
        document.getElementById(`d${domId}`)?.remove()
      })

    return () => {
      alive.current = false
    }
  }, [definition, domId])

  if (loading) {
    return (
      <div style={{ padding: '48px 0', textAlign: 'center', fontSize: 14, color: 'var(--muted)' }} aria-live="polite">
        Drawing the diagram…
      </div>
    )
  }

  if (error) {
    return (
      <div>
        <div
          role="alert"
          style={{
            padding: '12px 14px',
            border: '1px solid var(--accent-line)',
            background: 'var(--accent-soft)',
            borderRadius: 'var(--radius-md)',
            fontSize: 13.5,
            lineHeight: 1.6,
            color: 'var(--ink)',
            marginBottom: 14,
          }}
        >
          <strong style={{ color: 'var(--accent-text-sm)' }}>
            The diagram could not be drawn.
          </strong>{' '}
          Showing the source instead — the flow it describes is unchanged.
          <div className="font-mono-num" style={{ marginTop: 6, fontSize: 12, color: 'var(--muted)' }}>
            {error}
          </div>
        </div>
        <DiagramSource definition={definition} />
      </div>
    )
  }

  return (
    <figure style={{ margin: 0 }}>
      <div
        role="img"
        aria-label={label}
        style={{
          overflow: 'auto',
          background: 'var(--canvas)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          padding: 16,
          // Bounded so the dialog never becomes an endless page, but generous:
          // the diagram scrolls inside here rather than the diagram deciding the
          // layout.
          maxHeight: 'clamp(320px, 58vh, 680px)',
        }}
      >
        <ScaledSvg svg={svg} zoom={zoom} />
      </div>
    </figure>
  )
}

/**
 * Sizes mermaid's SVG for reading.
 *
 * FIT TO WIDTH, SCROLL VERTICALLY — chosen after measuring, not by taste. A
 * flowchart's aspect ratio falls out of its graph structure, so these land
 * anywhere from a 1:3 tower to a 16:1 ribbon. Two approaches were tried and
 * rejected:
 *
 *  - Letting the diagram set its own size: mermaid's inline pixel `max-width`
 *    meant a wide diagram simply overflowed and a tall one made the dialog
 *    endless.
 *  - Fitting the whole thing into a fixed box: the shape was visible but a
 *    3000px-wide flow scaled to about a tenth of design size, which is a picture
 *    of a diagram rather than a readable one.
 *
 * So: width is capped at the container and NEVER upscaled past natural size, and
 * the height is whatever it needs — you scroll down through the stages, which is
 * both how the flow reads and how people scroll anyway. Zoom multiplies from
 * there for a close look at one stage.
 */
function ScaledSvg({ svg, zoom }) {
  const host = useRef(null)

  useEffect(() => {
    const el = host.current?.querySelector('svg')
    if (!el) return

    const apply = () => {
      const natural = el.viewBox?.baseVal?.width
      // MEASURE THE SCROLL CONTAINER, NOT OUR OWN BOX. The wrapper is inside an
      // `overflow: auto` parent, so its own clientWidth grows to fit whatever the
      // SVG currently is — measuring it means measuring the thing being sized,
      // and the value never comes back down. On a narrow screen that left the
      // diagram at natural width, overflowing sideways. The scroll container's
      // width is fixed by layout, so it is the honest number.
      const scroller = host.current?.parentElement
      if (!natural || !scroller) return
      const pad = getComputedStyle(scroller)
      const available =
        scroller.clientWidth -
        (parseFloat(pad.paddingLeft) || 0) -
        (parseFloat(pad.paddingRight) || 0)
      if (available <= 0) return

      // min() keeps a narrow diagram at its own size rather than blowing it up
      // to fill the pane, which only makes the strokes clumsy.
      const width = Math.round(Math.min(natural, available) * zoom)
      el.removeAttribute('height')
      el.style.maxWidth = 'none'
      el.style.width = `${width}px`
      el.style.height = 'auto'
      el.setAttribute('preserveAspectRatio', 'xMidYMid meet')
    }

    apply()
    // The dialog is responsive, so a resize has to re-fit. Observing the
    // scroller (not the wrapper) also avoids an observer loop.
    const scroller = host.current?.parentElement
    const observer = new ResizeObserver(apply)
    if (scroller) observer.observe(scroller)
    return () => observer.disconnect()
  }, [svg, zoom])

  return (
    <div
      ref={host}
      style={{ width: '100%', minWidth: 0 }}
      // Mermaid output, sanitised by its own `strict` security level.
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  )
}

/** The definition as selectable text — for pasting into a deck or a doc. */
export function DiagramSource({ definition }) {
  return (
    <pre
      style={{
        margin: 0,
        padding: 14,
        overflowX: 'auto',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12.5,
        lineHeight: 1.6,
        color: 'var(--ink)',
        whiteSpace: 'pre',
      }}
    >
      <code>{definition}</code>
    </pre>
  )
}
