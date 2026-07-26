import { lazy, Suspense, useEffect, useState } from 'react'

import { useMoodSearch } from '../../controllers/useMoodSearch'
import { useStatusToast } from '../../hooks/useStatusToast'
import MoodBaselineLab from '../mood/MoodBaselineLab'
import MoodClarify from '../mood/MoodClarify'
import MoodDoorway from '../mood/MoodDoorway'
import MoodListenerPicker from '../mood/MoodListenerPicker'
import MoodSafety from '../mood/MoodSafety'
import MoodShelves from '../mood/MoodShelves'
import MoodStarters from '../mood/MoodStarters'
import { Button, Icon } from '../primitives'
import { useToast } from '../toast/useToast'

/**
 * Mood-First Search lens.
 *
 * Composition only — the flow lives in `useMoodSearch`, and this file maps that
 * state onto components.
 *
 * ONE SURFACE, FOUR STATES. `empty | clarify | shelves | safety` all render
 * here, switching on `state.mode` off the response. They are not separate routes
 * and must not become them: the lens keeps one URL so backing out of results
 * never lands the listener on the clarifying question again, which would read as
 * the app not having heard them.
 */
/**
 * The walkthrough is loaded on demand. It carries a diagram renderer that is
 * larger than the entire rest of the app, and it is opened by choice, once, to
 * explain the surface — so it has no business in the bundle everyone downloads
 * just to run a search.
 */
const MoodFlowDialog = lazy(() => import('../mood/MoodFlowDialog'))

function SearchBox({ initial, onSearch, loading }) {
  const [text, setText] = useState(initial || '')

  // A starter tap sets the query upstream; reflect it so the box always shows
  // what was actually searched.
  useEffect(() => {
    setText(initial || '')
  }, [initial])

  const submit = (event) => {
    event.preventDefault()
    if (text.trim()) onSearch(text)
  }

  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <label htmlFor="mood-query" className="label-upper" style={{ fontSize: 11 }}>
        How do you want this to feel?
      </label>

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', maxWidth: 620 }}>
        <input
          id="mood-query"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="something that feels like a rainy Sunday after heartbreak"
          autoComplete="off"
          style={{
            flex: 1,
            minWidth: 220,
            minHeight: 44,
            background: 'var(--canvas)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--ink)',
            padding: '0 16px',
            fontFamily: 'var(--font-sans)',
            fontSize: 16,
          }}
        />
        <Button variant="primary" type="submit" disabled={loading || !text.trim()}>
          {loading ? 'Searching…' : 'Search'}
        </Button>
      </div>

      <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch' }}>
        No genres and no browse grid — describe the feeling, in English or Hinglish.
      </p>
    </form>
  )
}

export default function MoodSearchTab() {
  const mood = useMoodSearch()
  const toast = useToast()
  const { mode, data } = mood.state

  // Declared before the early returns below, because hooks cannot be conditional.
  const [flowOpen, setFlowOpen] = useState(false)

  useStatusToast(mood.error, (e) => toast.error(`Mood search failed. ${e}`))

  // The doorway replaces the surface: once a listener has been sent to Ep 34,
  // the shelves are behind them until they come back.
  if (mood.playing) {
    return (
      <div style={{ paddingTop: 4 }}>
        <MoodDoorway playing={mood.playing} onBack={mood.closeDoorway} />
      </div>
    )
  }

  // Distress: retrieval never ran, and every demo control is suppressed. Someone
  // in crisis does not get a row of listener chips above the one thing that
  // matters.
  if (mode === 'safety') {
    return (
      <div style={{ paddingTop: 4, display: 'flex', flexDirection: 'column', gap: 28 }}>
        <MoodSafety message={data.safety_message} resources={data.support_resources} />
        <div>
          <Button variant="secondary" size="sm" onClick={mood.reset}>
            Start over
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div style={{ paddingTop: 4, display: 'flex', flexDirection: 'column', gap: 36 }}>
      {/* The walkthrough. Secondary on purpose: the primary action on this
          surface is always searching, and the design system keeps red and the
          main CTA from competing. Sits above the query box so it is the same
          click whether the lens is empty or showing results. */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)', maxWidth: '58ch' }}>
          Every stage below is inspectable — the parse, the three readings, what
          safety blocks before anything is ranked, and where the entry point comes
          from.
        </p>
        <Button variant="secondary" onClick={() => setFlowOpen(true)}>
          <Icon name="shuffle" size={16} />
          See the full flow
        </Button>
      </div>

      {flowOpen && (
        <Suspense fallback={null}>
          <MoodFlowDialog onClose={() => setFlowOpen(false)} />
        </Suspense>
      )}

      <SearchBox initial={mood.lastText} onSearch={mood.search} loading={mood.loading} />

      <MoodListenerPicker
        profiles={mood.profiles}
        value={mood.profileId}
        onChange={mood.pickProfile}
        disabled={mood.loading}
      />

      {mode === 'empty' && (
        <MoodStarters
          starters={mood.starters}
          onPick={mood.search}
          disabled={mood.loading}
          ready={mood.catalogReady}
          error={mood.catalogError}
        />
      )}

      {mode === 'clarify' && (
        <MoodClarify
          question={data.clarifying_question}
          onAnswer={mood.answer}
          busy={mood.loading}
        />
      )}

      {mode === 'shelves' && (
        <>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: 16,
              flexWrap: 'wrap',
            }}
          >
            <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)', maxWidth: '64ch' }}>
              That feeling reads three ways, so here are all three. Your pick is the
              answer — nothing was guessed.
            </p>
            {data.latency_ms != null && (
              <span className="font-mono-num" style={{ fontSize: 12.5, color: 'var(--dim)' }}>
                {data.latency_ms}ms
              </span>
            )}
          </div>

          <MoodShelves
            shelves={data.shelves}
            sliders={mood.sliders}
            onRefine={mood.refine}
            onOpen={mood.open}
            refining={mood.refining}
          />
        </>
      )}

      {/* Last, and folded shut. The genre baseline is the argument, not a
          feature — see MoodBaselineLab. */}
      <MoodBaselineLab queryId={mood.queryId} lastText={mood.lastText} />
    </div>
  )
}
