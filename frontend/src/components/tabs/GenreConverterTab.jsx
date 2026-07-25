import { useEffect, useMemo, useState } from 'react'

import { MAX_CHARS, MIN_CHARS, SAMPLE_SOURCE } from '../../config/genre'
import { useGenreConverter } from '../../controllers/useGenreConverter'
import FidelityReport from '../genre/FidelityReport'
import GenrePicker from '../genre/GenrePicker'
import RewriteView from '../genre/RewriteView'
import RunStatus from '../genre/RunStatus'
import SkeletonView from '../genre/SkeletonView'
import { Button, Tabs } from '../primitives'

const RESULT_TABS = [
  { id: 'rewrite', label: 'Rewrite' },
  { id: 'fidelity', label: 'Fidelity' },
  { id: 'skeleton', label: 'Plot skeleton' },
]

/**
 * Genre Converter lens.
 *
 * Rewrites a short story into another genre and scores how much of the original
 * plot survived. Composition only — the job lifecycle lives in
 * `useGenreConverter`, and this file maps that state onto components.
 */
export default function GenreConverterTab() {
  const c = useGenreConverter()
  const [view, setView] = useState('rewrite')

  // A finished extract has no rewrite to show, so land on the skeleton instead.
  useEffect(() => {
    if (c.result) setView(c.kind === 'extract' ? 'skeleton' : 'rewrite')
  }, [c.result, c.kind])

  /** Beats the verifier could not find in the prose, for the skeleton table. */
  const droppedBeats = useMemo(() => {
    const detail = c.result?.detail
    if (!detail) return []
    return [
      ...new Set([...(detail.missing_load_bearing ?? []), ...Object.keys(detail.beat_notes ?? {})]),
    ]
  }, [c.result])

  const overLimit = c.tooLong
  const counterColor = c.tooShort || overLimit ? 'var(--accent-text-sm)' : 'var(--muted)'

  return (
    <div style={{ marginTop: 32, display: 'flex', flexDirection: 'column', gap: 40 }}>
      <header style={{ maxWidth: '64ch' }}>
        <h2 style={{ margin: '0 0 8px', fontSize: 22, fontWeight: 600, color: 'var(--ink)' }}>
          Rewrite a story in another genre
        </h2>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: 'var(--muted)' }}>
          The plot is extracted into a genre-neutral skeleton, rewritten scene by scene in
          the target genre, then checked beat by beat against the page. You get the rewrite
          and a number for how much of the story survived it.
        </p>
      </header>

      {/* -------------------------------------------------------- source --- */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
          <label htmlFor="sgc-source" className="label-upper" style={{ fontSize: 11 }}>
            Source story
          </label>
          <button
            type="button"
            onClick={() => c.setSource(SAMPLE_SOURCE)}
            disabled={c.running}
            style={{
              background: 'none',
              border: 'none',
              padding: '4px 0',
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--ink)',
              textDecoration: 'underline',
              textUnderlineOffset: 3,
              cursor: c.running ? 'not-allowed' : 'pointer',
              opacity: c.running ? 0.5 : 1,
            }}
          >
            Use the sample story
          </button>
        </div>

        <textarea
          id="sgc-source"
          value={c.source}
          onChange={(e) => c.setSource(e.target.value)}
          disabled={c.running}
          spellCheck={false}
          placeholder="Paste a complete short story — beginning, middle, and an ending that lands."
          style={{
            width: '100%',
            minHeight: 260,
            boxSizing: 'border-box',
            resize: 'vertical',
            fontFamily: 'var(--font-mono)',
            fontSize: 14,
            lineHeight: 1.7,
            color: 'var(--ink)',
            background: c.running ? 'var(--surface)' : 'var(--canvas)',
            border: `1px solid ${overLimit ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 'var(--radius-md)',
            padding: 16,
          }}
        />

        <div className="font-mono-num" style={{ fontSize: 13, color: counterColor }}>
          {c.chars.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters
          {c.chars === 0 && <span style={{ color: 'var(--muted)' }}> · minimum {MIN_CHARS}</span>}
          {c.tooShort && <span> · too short to have a plot (minimum {MIN_CHARS})</span>}
          {overLimit && <span> · over the limit for this pipeline</span>}
        </div>
      </section>

      {/* --------------------------------------------------------- genre --- */}
      <GenrePicker
        genres={c.genres}
        value={c.genre}
        onChange={c.setGenre}
        disabled={c.running}
        error={c.genresError}
      />

      {/* ------------------------------------------------------- actions --- */}
      <section style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <Button variant="primary" onClick={c.convert} disabled={!c.canRun}>
          {c.running && c.kind === 'convert' ? 'Converting…' : 'Convert story'}
        </Button>
        <Button variant="secondary" onClick={c.extract} disabled={!c.canRun}>
          {c.running && c.kind === 'extract' ? 'Extracting…' : 'Extract skeleton only'}
        </Button>
        {c.blocker && !c.running && (
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>{c.blocker}</span>
        )}
        {!c.blocker && !c.running && (
          <span style={{ fontSize: 13, color: 'var(--muted)' }}>
            Conversion takes five to eight minutes. Extraction takes about twenty seconds.
          </span>
        )}
      </section>

      {/* -------------------------------------------------------- states --- */}
      {c.running && <RunStatus job={c.job} elapsed={c.elapsed} onStop={c.stopWatching} />}

      {c.error && (
        <div
          role="alert"
          style={{
            padding: '16px 18px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--danger)',
            background: 'var(--danger-bg)',
            color: 'var(--ink)',
            fontSize: 14,
            lineHeight: 1.6,
            maxWidth: '64ch',
          }}
        >
          <strong>The conversion failed.</strong> {c.error}
        </div>
      )}

      {!c.running && !c.result && !c.error && (
        <div
          style={{
            padding: '48px 24px',
            border: '1px dashed var(--border)',
            borderRadius: 'var(--radius-lg)',
            textAlign: 'center',
            color: 'var(--muted)',
          }}
        >
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)', marginBottom: 6 }}>
            No conversion yet
          </div>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6 }}>
            Paste a story and pick a genre. Try{' '}
            <strong style={{ color: 'var(--ink)' }}>Extract skeleton only</strong> first if you
            want to see what the pipeline thinks the plot is before paying for a rewrite.
          </p>
        </div>
      )}

      {/* -------------------------------------------------------- result --- */}
      {c.result && !c.running && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
              {c.kind === 'extract'
                ? 'Plot skeleton'
                : `Rewritten as ${c.result.genre}`}
            </h3>
            <button
              type="button"
              onClick={c.reset}
              style={{
                minHeight: 44,
                padding: '0 18px',
                background: 'var(--canvas)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--ink)',
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Clear result
            </button>
          </div>

          {c.kind === 'convert' ? (
            <>
              <Tabs
                tabs={RESULT_TABS}
                active={view}
                onChange={setView}
              />
              {view === 'rewrite' && (
                <RewriteView text={c.result.rewritten} genre={c.result.genre} />
              )}
              {view === 'fidelity' && (
                <FidelityReport
                  detail={c.result.detail}
                  skeleton={c.result.source_skeleton}
                  words={c.result.words}
                  seconds={c.result.seconds}
                />
              )}
              {view === 'skeleton' && (
                <SkeletonView skeleton={c.result.source_skeleton} dropped={droppedBeats} />
              )}
            </>
          ) : (
            <SkeletonView skeleton={c.result.skeleton} lint={c.result.lint} />
          )}
        </section>
      )}
    </div>
  )
}
