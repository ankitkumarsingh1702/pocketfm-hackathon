import { useEffect, useRef, useState } from 'react'

import Button from './Button'
import Icon from './Icon'

/**
 * A live, CLI-style run log for an agentic lens.
 *
 * Streams one line per event (system notes, phase changes, and each agent's
 * score as it lands) into a scrollable, monospace console — so a run reads like
 * a terminal, not an opaque spinner. Auto-scrolls while the user is at the
 * bottom, but yields if they scroll up to read. Keyboard-focusable and exposed
 * to assistive tech as a polite live region.
 *
 * Visual system: soft-surface panel, thin border, Lexend header, mono body,
 * soft-red only for phase markers / status / scores — never colour alone.
 *
 * @param {{
 *   log: {id:number, kind:string, text:string, detail?:string, score?:number, cached?:boolean}[],
 *   running: boolean,
 *   progress?: {label?:string, done?:number, total?:number},
 *   onStop?: () => void,
 *   title?: string,
 *   defaultOpen?: boolean,
 * }} props
 */
export default function AgentLogConsole({
  log = [],
  running = false,
  progress,
  onStop,
  title = 'Agent activity',
  defaultOpen = true,
}) {
  const [open, setOpen] = useState(defaultOpen)
  const bodyRef = useRef(null)
  const stick = useRef(true)

  // Re-expand automatically whenever a new run starts.
  useEffect(() => {
    if (running) setOpen(true)
  }, [running])

  // Follow the tail while the user is parked at the bottom; assigning scrollTop
  // (not smooth-scrolling) keeps this calm and reduced-motion friendly.
  useEffect(() => {
    const el = bodyRef.current
    if (!el || !open || !stick.current) return
    el.scrollTop = el.scrollHeight
  }, [log, open])

  const onScroll = () => {
    const el = bodyRef.current
    if (!el) return
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 48
  }

  const pct =
    progress && progress.total ? Math.min(100, Math.round((progress.done / progress.total) * 100)) : 0
  const count = log.length

  return (
    <section aria-label={title} style={styles.shell}>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span
            aria-hidden="true"
            style={{ ...styles.dot, background: running ? 'var(--accent)' : 'var(--muted)' }}
          />
          <span className="label-upper" style={{ fontSize: 11 }}>
            {title}
          </span>
          <span style={styles.status}>{running ? 'Live' : count ? 'Finished' : 'Idle'}</span>
        </div>
        <div style={styles.headerRight}>
          {progress?.total ? (
            <span style={styles.count}>
              {progress.label ? `${progress.label} · ` : ''}
              {progress.done}/{progress.total}
            </span>
          ) : count ? (
            <span style={styles.count}>{count} lines</span>
          ) : null}
          {running && onStop && (
            <Button variant="secondary" size="sm" onClick={onStop}>
              <Icon name="stop" size={14} /> Stop
            </Button>
          )}
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            style={styles.toggle}
            aria-expanded={open}
          >
            {open ? 'Hide' : 'Show'}
          </button>
        </div>
      </div>

      {running && progress?.total ? (
        <div style={styles.track} aria-hidden="true">
          <div style={{ ...styles.bar, width: `${pct}%` }} />
        </div>
      ) : (
        <div style={styles.rule} aria-hidden="true" />
      )}

      {open && (
        <div
          ref={bodyRef}
          onScroll={onScroll}
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label={`${title} log`}
          tabIndex={0}
          style={styles.body}
        >
          {count === 0 ? (
            <div style={styles.waiting}>Waiting for the first event…</div>
          ) : (
            log.map((line) => <LogLine key={line.id} line={line} />)
          )}
        </div>
      )}
    </section>
  )
}

const GLYPH = {
  system: '·',
  phase: '❯',
  agent: '▸',
  ok: '✓',
  done: '✓',
  error: '✕',
}

function LogLine({ line }) {
  const glyphColor =
    line.kind === 'phase' || line.kind === 'ok' || line.kind === 'done' || line.kind === 'error'
      ? 'var(--accent-text-sm)'
      : 'var(--muted)'
  const strong = line.kind === 'phase' || line.kind === 'done'
  return (
    <div style={styles.line}>
      <span aria-hidden="true" style={{ ...styles.glyph, color: glyphColor }}>
        {GLYPH[line.kind] || '·'}
      </span>
      <span style={styles.lineMain}>
        <span
          style={{
            color: line.kind === 'system' ? 'var(--muted)' : 'var(--ink)',
            fontWeight: strong ? 600 : 400,
          }}
        >
          {line.text}
        </span>
        {line.cached && <span style={styles.tag}>cached</span>}
        {line.detail && line.kind !== 'ok' && <span style={styles.detail}>{line.detail}</span>}
      </span>
      {line.detail && line.kind === 'ok' && (
        <span style={styles.previewDetail} title={line.detail}>
          {line.detail}
        </span>
      )}
    </div>
  )
}

const styles = {
  shell: {
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    background: 'var(--surface)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    padding: '10px 14px',
    flexWrap: 'wrap',
  },
  headerLeft: { display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 },
  headerRight: { display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' },
  dot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },
  status: { fontSize: 12, color: 'var(--muted)', fontFamily: 'var(--font-mono)' },
  count: {
    fontSize: 12,
    color: 'var(--muted)',
    fontFamily: 'var(--font-mono)',
    fontVariantNumeric: 'tabular-nums',
  },
  toggle: {
    background: 'none',
    border: 'none',
    color: 'var(--accent-text-sm)',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    padding: '4px 2px',
    minHeight: 32,
  },
  track: { height: 3, background: 'var(--grey-200)', overflow: 'hidden' },
  bar: {
    height: '100%',
    background: 'var(--accent)',
    transition: 'width var(--dur-med, 240ms) var(--ease-standard, ease)',
  },
  rule: { height: 1, background: 'var(--border)' },
  body: {
    maxHeight: 340,
    overflowY: 'auto',
    padding: '12px 14px',
    fontFamily: 'var(--font-mono)',
    fontSize: 12.5,
    lineHeight: 1.7,
    color: 'var(--ink)',
    background: 'var(--canvas, #fff)',
  },
  waiting: { color: 'var(--muted)', fontStyle: 'italic' },
  line: { display: 'flex', gap: 8, alignItems: 'baseline' },
  glyph: { flexShrink: 0, width: 12, textAlign: 'center' },
  lineMain: { display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap', minWidth: 0, flex: 1 },
  detail: {
    color: 'var(--muted)',
    fontVariantNumeric: 'tabular-nums',
  },
  previewDetail: {
    color: 'var(--muted)',
    maxWidth: '52%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flexShrink: 0,
  },
  tag: {
    fontSize: 10,
    fontWeight: 600,
    color: 'var(--muted)',
    border: '1px solid var(--border)',
    borderRadius: 999,
    padding: '0 6px',
    lineHeight: '16px',
  },
}
