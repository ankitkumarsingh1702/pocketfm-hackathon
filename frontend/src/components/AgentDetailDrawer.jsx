import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

import { initialsFor } from '../utils/agentDirectory'
import { Button, Disclosure } from './primitives'

/**
 * AgentDetailDrawer — a read-only right-side drawer showing one agent's full
 * story: profile, context, memory and history. Generic shell used for both the
 * reasoning agents and the 1000s of persona/listener agents; the caller supplies
 * the section content (facts, chip groups, system prompt, history items).
 *
 * Rendered into <body> via a portal so no transformed ancestor can capture the
 * fixed positioning. Escape and the scrim close it; focus moves to Close on open.
 */
export default function AgentDetailDrawer({
  onClose,
  name,
  subtitle,
  badge,
  hub = false,
  description,
  facts = [],
  chipGroups = [],
  memoryDescription,
  systemPrompt,
  history,
  primaryAction,
  ask,
  callInfo,
}) {
  const closeRef = useRef(null)
  const [shown, setShown] = useState(false)
  const [draft, setDraft] = useState('')
  const origin = typeof window !== 'undefined' ? window.location.origin : ''

  useEffect(() => {
    closeRef.current?.focus()
    const raf = requestAnimationFrame(() => setShown(true))
    function onKey(e) {
      if (e.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  const cleanFacts = facts.filter((f) => f && f.value !== undefined && f.value !== null && f.value !== '')

  return createPortal(
    <div
      role="presentation"
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', justifyContent: 'flex-end' }}
    >
      <div
        onClick={onClose}
        aria-hidden="true"
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(17,17,17,0.28)',
          opacity: shown ? 1 : 0,
          transition: 'opacity var(--dur-fast, 150ms) var(--ease-standard, ease)',
        }}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${name || 'Agent'} profile`}
        style={{
          position: 'relative',
          width: 'min(460px, 100%)',
          height: '100%',
          background: 'var(--surface-raised)',
          borderLeft: '1px solid var(--border)',
          boxShadow: 'var(--shadow-soft, 0 8px 28px rgba(17,17,17,0.12))',
          display: 'flex',
          flexDirection: 'column',
          transform: shown ? 'translateX(0)' : 'translateX(12px)',
          opacity: shown ? 1 : 0,
          transition: 'transform var(--dur-med, 320ms) var(--ease-standard, ease), opacity var(--dur-med, 320ms) var(--ease-standard, ease)',
        }}
      >
        {/* Header */}
        <header
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12,
            padding: '18px 20px',
            borderBottom: '1px solid var(--border)',
          }}
        >
          <span
            aria-hidden="true"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 44,
              height: 44,
              flexShrink: 0,
              borderRadius: 'var(--radius-sm)',
              fontFamily: 'var(--font-mono)',
              fontSize: 15,
              fontWeight: 600,
              color: hub ? 'var(--accent-text-sm)' : 'var(--ink)',
              background: hub ? 'var(--accent-soft)' : 'var(--surface)',
              border: `1px solid ${hub ? 'var(--accent-line)' : 'var(--border)'}`,
            }}
          >
            {initialsFor(name)}
          </span>
          <div style={{ minWidth: 0, flex: 1 }}>
            {badge && (
              <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 3 }}>
                {badge}
              </div>
            )}
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)', lineHeight: 1.2 }}>
              {name}
            </div>
            {subtitle && (
              <div style={{ fontSize: 13, color: 'var(--accent-text-sm)', fontWeight: 600, marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
          <button
            type="button"
            ref={closeRef}
            onClick={onClose}
            aria-label="Close"
            style={{
              flexShrink: 0,
              minHeight: 36,
              minWidth: 36,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--ink)',
              cursor: 'pointer',
              fontSize: 16,
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        </header>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 22 }}>
          {description && (
            <p style={{ margin: 0, fontSize: 14, color: 'var(--ink)', lineHeight: 1.6 }}>{description}</p>
          )}

          {ask && (
            <section
              style={{
                border: '1px solid var(--accent-line)',
                background: 'var(--accent-soft)',
                borderRadius: 'var(--radius-md)',
                padding: 14,
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
              }}
            >
              <div className="label-upper" style={{ fontSize: 10, color: 'var(--accent-text-sm)' }}>
                Ask this agent
              </div>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Post a teaser or hook — this agent reacts in character, and remembers it."
                rows={3}
                aria-label="Teaser for this agent"
                style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: 13.5,
                  color: 'var(--ink)',
                  background: 'var(--surface-raised)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '9px 11px',
                  resize: 'vertical',
                  lineHeight: 1.5,
                }}
              />
              <div>
                <Button size="sm" onClick={() => ask.onAsk?.(draft)} disabled={ask.loading || !draft.trim()}>
                  {ask.loading ? 'Reacting…' : 'Ask'}
                </Button>
              </div>
              {ask.error && <p style={{ margin: 0, fontSize: 12.5, color: 'var(--danger)' }}>{ask.error}</p>}
              {ask.data && <ReactionResult r={ask.data} />}
            </section>
          )}

          {cleanFacts.length > 0 && (
            <section>
              <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 10 }}>
                Profile
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                  gap: '12px 16px',
                }}
              >
                {cleanFacts.map((f) => (
                  <div key={f.label} style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                    <span className="label-upper" style={{ fontSize: 9.5, color: 'var(--dim)' }}>{f.label}</span>
                    <span style={{ fontSize: 13.5, color: 'var(--ink)', fontWeight: 600, wordBreak: 'break-word' }}>
                      {f.value}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {chipGroups
            .filter((grp) => grp && (grp.items || []).length > 0)
            .map((grp) => (
              <section key={grp.label}>
                <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 8 }}>
                  {grp.label} · {grp.items.length}
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                  {grp.items.map((item, i) => (
                    <span
                      key={`${item}-${i}`}
                      style={{
                        fontSize: 11.5,
                        fontWeight: 500,
                        color: 'var(--muted)',
                        background: 'var(--surface)',
                        border: '1px solid var(--border)',
                        borderRadius: 'var(--radius-pill)',
                        padding: '4px 10px',
                        lineHeight: 1.2,
                      }}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </section>
            ))}

          {memoryDescription && (
            <section>
              <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 8 }}>
                Context
              </div>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.6 }}>
                {memoryDescription}
              </p>
            </section>
          )}

          {systemPrompt && (
            <section style={{ borderTop: '1px solid var(--border)', paddingTop: 4 }}>
              <Disclosure
                summary={<span className="label-upper" style={{ fontSize: 10.5 }}>System prompt · character memory</span>}
              >
                <p
                  style={{
                    margin: '6px 0 8px',
                    fontSize: 12.5,
                    color: 'var(--muted)',
                    lineHeight: 1.6,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {systemPrompt}
                </p>
              </Disclosure>
            </section>
          )}

          {history && (
            <section>
              <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 10 }}>
                {history.title || 'History'}
                {typeof history.count === 'number' ? ` · ${history.count}` : ''}
              </div>
              {history.loading && (
                <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>Reading memory…</p>
              )}
              {history.error && (
                <p style={{ margin: 0, fontSize: 13, color: 'var(--danger)' }}>{history.error}</p>
              )}
              {!history.loading && !history.error && (history.items || []).length === 0 && (
                <p style={{ margin: 0, fontSize: 13, color: 'var(--dim)', lineHeight: 1.5 }}>
                  {history.empty || 'No history yet.'}
                </p>
              )}
              {(history.items || []).length > 0 && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{history.items}</div>
              )}
            </section>
          )}

          {callInfo && (
            <section style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
              <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 8 }}>
                Call this agent
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <code style={CODE_STYLE}>agent://{callInfo.agentId}</code>
                <code style={{ ...CODE_STYLE, whiteSpace: 'pre-wrap' }}>
                  {`curl -X POST ${origin}/api/agents/${callInfo.agentId}/react \\
  -H 'Content-Type: application/json' \\
  -d '{"text":"your teaser"}'`}
                </code>
                <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.55 }}>
                  MCP server:{' '}
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: 11.5, color: 'var(--ink)' }}>
                    {origin}/mcp/
                  </code>{' '}
                  — add it to your MCP client (no login). Tools:
                </div>
                <ul
                  style={{
                    margin: 0,
                    paddingLeft: 16,
                    fontSize: 12,
                    color: 'var(--muted)',
                    lineHeight: 1.7,
                    listStyle: 'disc',
                  }}
                >
                  {[
                    ['ask_agent', 'talk to this agent — it reacts in character and remembers'],
                    ['get_agent · list_agents', 'read a profile / search the roster'],
                    ['edit_agent', 'change a profile (e.g. move them to Delhi)'],
                    ['create_agent', 'add a new listener to the population'],
                    ['forget_agent', "clear an agent's memory"],
                    ['audience_overview', 'population stats + available filters'],
                  ].map(([tool, desc]) => (
                    <li key={tool}>
                      <code
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: 11.5,
                          color: 'var(--accent-text-sm)',
                        }}
                      >
                        {tool}
                      </code>{' '}
                      — {desc}
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          {primaryAction && (
            <div style={{ marginTop: 'auto', paddingTop: 8 }}>
              <Button variant="secondary" size="sm" onClick={primaryAction.onClick}>
                {primaryAction.label}
              </Button>
            </div>
          )}
        </div>
      </aside>
    </div>,
    document.body,
  )
}

const CODE_STYLE = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11.5,
  color: 'var(--ink)',
  background: 'var(--surface)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  padding: '8px 10px',
  overflowX: 'auto',
}

/** The live in-character reaction returned by "Ask this agent". */
function ReactionResult({ r }) {
  const facts = [
    r.will_listen ? 'will play' : 'skips',
    r.sentiment,
    r.engagement,
    r.hook_score != null ? `hook ${r.hook_score}` : null,
    r.emotion,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <div
      style={{
        background: 'var(--surface-raised)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      {facts && <div style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--accent-text-sm)' }}>{facts}</div>}
      {r.comment && (
        <div style={{ fontSize: 13, color: 'var(--ink)', lineHeight: 1.5, fontStyle: 'italic' }}>“{r.comment}”</div>
      )}
      {r.reasoning && (
        <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>
          <strong style={{ color: 'var(--ink)' }}>Why:</strong> {r.reasoning}
        </div>
      )}
      {r.memory_note && (
        <div style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5 }}>
          <strong style={{ color: 'var(--ink)' }}>Remembered:</strong> {r.memory_note}
        </div>
      )}
    </div>
  )
}
