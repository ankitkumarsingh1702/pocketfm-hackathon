import { useEffect, useMemo, useRef, useState } from 'react'

import { MAX_CHARS, MIN_CHARS } from '../../config/genre'
import { useGenreConverter } from '../../controllers/useGenreConverter'
import { useStatusToast } from '../../hooks/useStatusToast'
import FidelityReport from '../genre/FidelityReport'
import GenrePicker from '../genre/GenrePicker'
import HistoryView from '../genre/HistoryView'
import LiveScenes from '../genre/LiveScenes'
import RewriteView from '../genre/RewriteView'
import RunStatus from '../genre/RunStatus'
import SkeletonView from '../genre/SkeletonView'
import { Button, Disclosure, Tabs } from '../primitives'
import StoryPicker from '../StoryPicker'
import { useToast } from '../toast/useToast'

const MODE_TABS = [
  { id: 'convert', label: 'Convert' },
  { id: 'history', label: 'History' },
]

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
  const toast = useToast()
  const [mode, setMode] = useState('convert')
  const [view, setView] = useState('rewrite')

  // .txt upload: read client-side, land the text in the source box.
  const fileInputRef = useRef(null)

  async function pickFile(event) {
    const file = event.target.files?.[0]
    event.target.value = '' // so picking the same file again still fires
    if (!file) return
    if (!/\.txt$/i.test(file.name)) {
      toast.error(`${file.name} is not a .txt file — export the story as plain text first.`)
      return
    }
    try {
      const text = await file.text()
      c.setSource(text)
      toast.success(`Loaded ${file.name} into the source box.`)
    } catch {
      toast.error(`Could not read ${file.name}. Try again or paste the text instead.`)
    }
  }

  // Announce the job's outcomes as they land.
  useStatusToast(c.genresError, (e) => toast.error(`Could not load the genre packs. ${e}`))
  useStatusToast(c.error, (e) => toast.error(`The conversion failed. ${e}`))
  useStatusToast(c.result, (r) => {
    if (c.kind === 'extract') {
      toast.success('Plot skeleton extracted.')
    } else {
      toast.success(
        `Rewrite finished — ${Math.round((r.detail?.fidelity ?? 0) * 100)}% of the plot survived.`,
      )
    }
  })

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

  // Live pieces stay up while the job runs and after it fails; the finished
  // view replaces them only once there is a whole result to show.
  const showLive = !c.result && (c.running || Boolean(c.error))

  return (
    <div style={{ paddingTop: 4, display: 'flex', flexDirection: 'column', gap: 36 }}>
      {/* Convert / History switch. Both stay mounted so a running job's live
          view survives a look at the history. */}
      <Tabs tabs={MODE_TABS} active={mode} onChange={setMode} />

      <div hidden={mode !== 'convert'} style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
      {/* -------------------------------------------------------- source --- */}
      <section style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <label htmlFor="sgc-source" className="label-upper" style={{ fontSize: 11 }}>
            Source story
          </label>
          <input ref={fileInputRef} type="file" accept=".txt,text/plain" onChange={pickFile} hidden />
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={c.running}
          >
            Upload a .txt
          </Button>
        </div>

        <StoryPicker
          onSelect={(s) => c.setSource(`${s.title}\n\n${s.text}`)}
          label="Load a ready-made story to convert"
        />

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

      {/* ----------------------------------------------------- live work --- */}
      {/* Shown while the job runs, and kept on screen if it fails: the pieces
          that did finish are what make a failure legible. Once `result` lands
          the finished view below takes over and this comes down. */}
      {showLive && c.partial.skeleton && c.kind === 'convert' && (
        /* During a conversion the skeleton is context, not the destination —
           it folds to one line so the scenes below keep the spotlight. */
        <section style={{ borderTop: '1px solid var(--border)' }}>
          <Disclosure
            summary={
              <span style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>
                  Plot skeleton — extracted
                </span>
                <span className="font-mono-num" style={{ fontSize: 12.5, color: 'var(--muted)' }}>
                  {c.partial.skeleton.counts?.beats} beats ·{' '}
                  {c.partial.skeleton.counts?.load_bearing} load-bearing
                </span>
              </span>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14, paddingBottom: 8 }}>
              <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch', lineHeight: 1.6 }}>
                Extracted from your story, with names and genre language stripped out. This is
                the only thing the rewrite is allowed to keep.
              </p>
              <SkeletonView skeleton={c.partial.skeleton} lint={c.partial.lint} />
            </div>
          </Disclosure>
        </section>
      )}

      {showLive && c.partial.skeleton && c.kind === 'extract' && (
        <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <h3 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
              Plot skeleton
            </h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch', lineHeight: 1.6 }}>
              Extracted from your story, with names and genre language stripped out. This is
              the only thing the rewrite is allowed to keep.
            </p>
          </div>
          <SkeletonView skeleton={c.partial.skeleton} lint={c.partial.lint} />
        </section>
      )}

      {showLive && c.kind === 'convert' && (
        <LiveScenes
          plan={c.partial.scene_plan}
          scenes={c.partial.scenes}
          active={c.activeScene}
          genre={c.job?.genre ?? c.genre}
        />
      )}

      {c.error && (
        <div
          role="alert"
          style={{
            padding: '16px 18px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--accent-line)',
            background: 'var(--accent-soft)',
            color: 'var(--ink)',
            fontSize: 14,
            lineHeight: 1.6,
            maxWidth: '64ch',
            display: 'flex',
            gap: 12,
            alignItems: 'flex-start',
          }}
        >
          <span aria-hidden="true" style={{ color: 'var(--accent-text-sm)', fontWeight: 700 }}>
            ✕
          </span>
          <span>
            <strong style={{ color: 'var(--accent-text-sm)' }}>The conversion failed.</strong>{' '}
            {c.error}
          </span>
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
            <Button variant="secondary" onClick={c.reset}>
              Clear result
            </Button>
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

      <div hidden={mode !== 'history'}>
        <HistoryView
          active={mode === 'history'}
          refreshKey={c.kind === 'convert' ? c.result : null}
        />
      </div>
    </div>
  )
}
