import { useEffect, useRef, useState } from 'react'

import {
  MOOD_FLOW_CONSTANTS,
  MOOD_FLOW_NARRATION,
  MOOD_FLOW_QA,
  MOOD_FLOW_VIEWS,
} from '../../config/moodFlow'
import { Button, Icon, Tabs } from '../primitives'
// Direct import, not via the primitives barrel: see the note there.
import MermaidDiagram, { DiagramSource } from '../primitives/MermaidDiagram'

/**
 * The walkthrough. A full-surface dialog holding the end-to-end flow of
 * Mood-First Search as a set of diagrams, plus the notes needed to talk through
 * it live.
 *
 * Built for being presented from, not just read:
 *  - four views, coarse to fine, so a question can be answered at the level it
 *    was asked rather than by scrolling one enormous diagram;
 *  - zoom, because a laptop driving a projector is the normal case;
 *  - the mermaid source is one click away for pasting into a deck;
 *  - speaker notes and the awkward questions sit beside the diagram, so there is
 *    no second window to alt-tab to mid-answer.
 *
 * A dialog rather than a route: the walkthrough explains the surface behind it,
 * and closing it must put you back exactly where you were, mid-query.
 */
export default function MoodFlowDialog({ onClose }) {
  const [view, setView] = useState(MOOD_FLOW_VIEWS[0].id)
  const [zoom, setZoom] = useState(1)
  const [showSource, setShowSource] = useState(false)
  const [copied, setCopied] = useState(false)
  const [notes, setNotes] = useState(false)

  const closeRef = useRef(null)
  const panelRef = useRef(null)

  // Focus the dismiss control on open, let Escape close, and keep Tab inside the
  // dialog — matching the drawer convention already used in AgentProfile.
  useEffect(() => {
    closeRef.current?.focus()

    function onKey(event) {
      if (event.key === 'Escape') {
        onClose?.()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = panelRef.current?.querySelectorAll(
        'button:not([disabled]), [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKey)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose])

  // Each view is its own diagram, so reset the reading state when it changes.
  useEffect(() => {
    setZoom(1)
    setShowSource(false)
  }, [view])

  const current = MOOD_FLOW_VIEWS.find((v) => v.id === view) ?? MOOD_FLOW_VIEWS[0]

  async function copySource() {
    try {
      await navigator.clipboard.writeText(current.definition)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      // Clipboard blocked (insecure origin, or denied): the source panel below
      // is the fallback, so open it rather than failing silently.
      setShowSource(true)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 'clamp(0px, 2vw, 28px)',
      }}
      role="presentation"
    >
      <button
        type="button"
        aria-label="Close the walkthrough"
        onClick={onClose}
        style={{
          position: 'absolute',
          inset: 0,
          border: 'none',
          background: 'rgba(14, 14, 14, 0.45)',
          cursor: 'pointer',
        }}
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="mood-flow-title"
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          width: '100%',
          maxWidth: 1180,
          maxHeight: '100%',
          background: 'var(--canvas)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: '0 24px 64px rgba(14, 14, 14, 0.18)',
          overflow: 'hidden',
        }}
      >
        {/* ------------------------------------------------------- head --- */}
        <header
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 16,
            padding: '20px clamp(16px, 3vw, 28px) 0',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: 1, minWidth: 220 }}>
            <div className="label-upper" style={{ fontSize: 11, marginBottom: 6 }}>
              How it works, end to end
            </div>
            <h2
              id="mood-flow-title"
              style={{ margin: 0, fontSize: 22, fontWeight: 600, color: 'var(--ink)' }}
            >
              Mood-First Search — the whole pipeline
            </h2>
          </div>
          <Button variant="secondary" onClick={onClose}>
            <span ref={closeRef} tabIndex={-1} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Icon name="close" size={16} />
              Close
            </span>
          </Button>
        </header>

        <div style={{ padding: '16px clamp(16px, 3vw, 28px) 0' }}>
          <Tabs
            tabs={MOOD_FLOW_VIEWS.map((v) => ({ id: v.id, label: v.label }))}
            active={view}
            onChange={setView}
          />
        </div>

        {/* ------------------------------------------------------- body --- */}
        <div
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: 'auto',
            padding: '20px clamp(16px, 3vw, 28px) 28px',
            display: 'flex',
            flexDirection: 'column',
            gap: 18,
          }}
        >
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.6, color: 'var(--muted)', maxWidth: '76ch' }}>
            {current.caption}
          </p>

          {/* Controls sit above the diagram: reachable on a projector without
              hunting, and they never overlay the thing being explained. */}
          {/* Default (not `sm`) size throughout: `sm` renders at 36px, and these
              are the controls someone reaches for on a phone or mid-presentation,
              so they need the 44px minimum. */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div role="group" aria-label="Zoom" style={{ display: 'flex', gap: 6 }}>
              <Button
                variant="secondary"
                onClick={() => setZoom((z) => Math.max(1, Math.round((z - 0.25) * 100) / 100))}
                disabled={zoom <= 1}
              >
                − Zoom out
              </Button>
              <Button
                variant="secondary"
                onClick={() => setZoom((z) => Math.min(3, Math.round((z + 0.25) * 100) / 100))}
                disabled={zoom >= 3}
              >
                + Zoom in
              </Button>
            </div>
            <span className="font-mono-num" style={{ fontSize: 12.5, color: 'var(--dim)', minWidth: 44 }}>
              {Math.round(zoom * 100)}%
            </span>

            <span style={{ flex: 1 }} />

            <Button variant="secondary" onClick={() => setNotes((n) => !n)}>
              {notes ? 'Hide speaker notes' : 'Speaker notes'}
            </Button>
            <Button variant="secondary" onClick={() => setShowSource((s) => !s)}>
              {showSource ? 'Hide source' : 'View source'}
            </Button>
            <Button variant="secondary" onClick={copySource}>
              {copied ? 'Copied' : 'Copy mermaid'}
            </Button>
          </div>

          <MermaidDiagram definition={current.definition} label={current.label} zoom={zoom} />

          {showSource && (
            <section>
              <div className="label-upper" style={{ fontSize: 11, marginBottom: 8 }}>
                Mermaid source — paste this into a deck or a doc
              </div>
              <DiagramSource definition={current.definition} />
            </section>
          )}

          {notes && (
            <section style={{ display: 'grid', gap: 22 }}>
              <div>
                <div className="label-upper" style={{ fontSize: 11, marginBottom: 10 }}>
                  Walking the panel through it
                </div>
                <ol style={{ margin: 0, paddingLeft: 20, display: 'grid', gap: 12 }}>
                  {MOOD_FLOW_NARRATION.map((n) => (
                    <li key={n.beat} style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--ink)' }}>
                      <strong style={{ fontWeight: 600 }}>{n.beat}. </strong>
                      {n.say}
                      <span style={{ display: 'block', fontSize: 12.5, color: 'var(--muted)', marginTop: 3 }}>
                        Point at: {n.point_at}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>

              <div>
                <div className="label-upper" style={{ fontSize: 11, marginBottom: 10 }}>
                  Questions they will ask
                </div>
                <dl style={{ margin: 0, display: 'grid', gap: 14 }}>
                  {MOOD_FLOW_QA.map((item) => (
                    <div key={item.question}>
                      <dt style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)', marginBottom: 3 }}>
                        {item.question}
                      </dt>
                      <dd style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--muted)' }}>
                        {item.answer}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>

              <div>
                <div className="label-upper" style={{ fontSize: 11, marginBottom: 10 }}>
                  The tuned numbers
                </div>
                <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13.5 }}>
                    <thead>
                      <tr style={{ textAlign: 'left', color: 'var(--muted)' }}>
                        <th style={cellHead}>What</th>
                        <th style={cellHead}>Value</th>
                        <th style={cellHead}>Why that number</th>
                      </tr>
                    </thead>
                    <tbody>
                      {MOOD_FLOW_CONSTANTS.map((c) => (
                        <tr key={c.name}>
                          <td style={{ ...cell, color: 'var(--ink)' }}>{c.name}</td>
                          <td style={{ ...cell, ...num }}>{c.value}</td>
                          <td style={{ ...cell, color: 'var(--muted)' }}>{c.why}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

const cellHead = {
  padding: '10px 14px',
  borderBottom: '1px solid var(--border)',
  fontWeight: 600,
  whiteSpace: 'nowrap',
}
const cell = { padding: '10px 14px', borderBottom: '1px solid var(--border)', verticalAlign: 'top' }
const num = { fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }
