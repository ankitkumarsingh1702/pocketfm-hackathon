import { useState } from 'react'

import { Disclosure } from '../primitives'

/**
 * The rewrite arriving, scene by scene.
 *
 * The pipeline plans every scene before it writes the first one, so the whole
 * shape of the job is knowable up front: this renders that plan immediately
 * and fills each row in as its prose lands.
 *
 * The prose itself is behind a per-scene accordion so the run stays scannable:
 * the scene being written and the most recently finished one are open — that
 * is where the action is — and every earlier scene folds to a one-line summary
 * (status, beats, word count) a reader can reopen at will. A manual toggle
 * always beats the automatic rule, so nothing snaps shut mid-read.
 */

/** One beat-id chip. Pivotal beats carry the same red dot the skeleton uses. */
function BeatChip({ id, pivotal, missing }) {
  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        padding: '2px 7px',
        borderRadius: 'var(--radius-sm)',
        border: `1px solid ${missing ? 'var(--accent-line)' : 'var(--border)'}`,
        background: missing ? 'var(--accent-soft)' : 'var(--canvas)',
        color: missing ? 'var(--accent-text-sm)' : 'var(--muted)',
        whiteSpace: 'nowrap',
      }}
    >
      {id}
      {pivotal && (
        <span aria-label=" (load-bearing)" style={{ marginLeft: 4, color: 'var(--accent-text-sm)', fontWeight: 700 }}>
          ●
        </span>
      )}
    </span>
  )
}

function StatusTag({ state }) {
  const copy = {
    written: { text: 'Written', color: 'var(--muted)', border: 'var(--border)' },
    writing: { text: 'Writing now', color: 'var(--accent-text-sm)', border: 'var(--accent-line)' },
    queued: { text: 'Queued', color: 'var(--dim)', border: 'var(--border)' },
  }[state]

  return (
    <span
      style={{
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: 'var(--tracking-label)',
        textTransform: 'uppercase',
        color: copy.color,
        border: `1px solid ${copy.border}`,
        borderRadius: 'var(--radius-pill)',
        padding: '3px 10px',
        whiteSpace: 'nowrap',
      }}
    >
      {copy.text}
    </span>
  )
}

/** The row header — all a reader needs while the scene is folded. */
function SceneSummary({ entry, scene, state, pivots, missing }) {
  return (
    <span style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
      <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)' }}>
        Scene {entry.scene}
      </span>
      <StatusTag state={state} />
      <span style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {(entry.beat_ids ?? []).map((id) => (
          <BeatChip key={id} id={id} pivotal={pivots.has(id)} missing={missing.has(id)} />
        ))}
      </span>
      {scene?.words != null && (
        <span className="font-mono-num" style={{ fontSize: 12.5, color: 'var(--dim)' }}>
          {scene.words} words
        </span>
      )}
    </span>
  )
}

/** The prose and its footnotes — what the accordion folds away. */
function SceneBody({ scene, state }) {
  return (
    <div style={{ paddingBottom: 8 }}>
      {scene?.retried && (
        <p style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--muted)', lineHeight: 1.6 }}>
          The first attempt left out a load-bearing beat, so it was written again with that
          beat quoted back.
        </p>
      )}

      {scene?.missing?.length > 0 && (
        <p style={{ margin: '0 0 8px', fontSize: 13, color: 'var(--accent-text-sm)', fontWeight: 600 }}>
          Still missing after the retry: {scene.missing.join(', ')}
        </p>
      )}

      {state === 'writing' && (
        <p style={{ margin: '2px 0 0', fontSize: 14, color: 'var(--muted)', lineHeight: 1.6 }}>
          Writing this scene now — roughly 200 to 350 words per beat, so it takes about a
          minute.
        </p>
      )}

      {scene?.prose && (
        <article
          style={{
            marginTop: 6,
            maxWidth: '68ch',
            fontSize: 16.5,
            lineHeight: 1.75,
            color: 'var(--ink)',
            whiteSpace: 'pre-wrap',
          }}
        >
          {scene.prose}
        </article>
      )}
    </div>
  )
}

export default function LiveScenes({ plan, scenes, active, genre }) {
  // A reader's explicit open/close beats the automatic focus rule.
  const [overrides, setOverrides] = useState({})

  if (!plan?.length) return null

  const written = new Map((scenes ?? []).map((s) => [s.scene, s]))
  const total = plan.length
  const doneCount = written.size
  const words = (scenes ?? []).reduce((sum, s) => sum + (s.words ?? 0), 0)
  const latestWritten = scenes?.length ? scenes[scenes.length - 1].scene : null

  const isOpen = (sceneNo) =>
    overrides[sceneNo] ?? (sceneNo === active || sceneNo === latestWritten)

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: 'var(--ink)' }}>
          {genre ? `The rewrite, as ${genre}` : 'The rewrite'}
        </h3>
        <span className="font-mono-num" style={{ fontSize: 13, color: 'var(--muted)' }}>
          {doneCount} of {total} scenes
          {words > 0 && ` · ${words.toLocaleString()} words so far`}
        </span>
      </div>

      <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch', lineHeight: 1.6 }}>
        Each scene is one model call, given only the beats it owns. The scene being written
        stays open; finished ones fold up — open any of them to read while the job runs.
      </p>

      <ol style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 0 }}>
        {plan.map((entry) => {
          const scene = written.get(entry.scene)
          const state = scene ? 'written' : entry.scene === active ? 'writing' : 'queued'
          const pivots = new Set(entry.load_bearing ?? [])
          const missing = new Set(scene?.missing ?? [])
          const summary = (
            <SceneSummary entry={entry} scene={scene} state={state} pivots={pivots} missing={missing} />
          )

          return (
            <li
              key={entry.scene}
              style={{
                borderTop: '1px solid var(--border)',
                padding: '6px 0',
                opacity: state === 'queued' ? 0.55 : 1,
              }}
            >
              {state === 'queued' ? (
                /* Nothing to unfold yet — a static row keeps the plan visible
                   without a control that does nothing. */
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minHeight: 44, padding: '8px 0' }}>
                  <span aria-hidden="true" style={{ flexShrink: 0, fontSize: 10, color: 'var(--dim)' }}>
                    ·
                  </span>
                  {summary}
                </div>
              ) : (
                <Disclosure
                  summary={summary}
                  open={isOpen(entry.scene)}
                  onToggle={(next) =>
                    setOverrides((current) => ({ ...current, [entry.scene]: next }))
                  }
                >
                  <SceneBody scene={scene} state={state} />
                </Disclosure>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
