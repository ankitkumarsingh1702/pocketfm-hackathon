import { useCallback, useEffect, useState } from 'react'

/**
 * The rewritten story.
 *
 * Measure is capped at ~68 characters and set at reading size — this is the one
 * surface in the studio whose content is meant to be read rather than scanned,
 * so it gets prose typography instead of the dashboard's data typography.
 */
export default function RewriteView({ text, genre }) {
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!copied) return undefined
    const timer = setTimeout(() => setCopied(false), 2000)
    return () => clearTimeout(timer)
  }, [copied])

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }, [text])

  const download = useCallback(() => {
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `rewrite-${genre}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }, [text, genre])

  const action = {
    minHeight: 44,
    padding: '0 18px',
    background: 'var(--canvas)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--ink)',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
  }

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        <button type="button" onClick={copy} style={action}>
          {copied ? 'Copied' : 'Copy text'}
        </button>
        <button type="button" onClick={download} style={action}>
          Download .txt
        </button>
        <span role="status" aria-live="polite" className="sr-only">
          {copied ? 'Rewrite copied to the clipboard' : ''}
        </span>
      </div>

      <article
        style={{
          maxWidth: '68ch',
          fontSize: 17,
          lineHeight: 1.75,
          color: 'var(--ink)',
          whiteSpace: 'pre-wrap',
        }}
      >
        {text}
      </article>
    </section>
  )
}
