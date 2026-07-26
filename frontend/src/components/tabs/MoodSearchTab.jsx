/**
 * Mood-First Search — the studio surface.
 *
 * One tab, four modes. `mode` comes straight off SearchResponse.mode — the view
 * never decides which screen to show, the contract does. Empty, clarify,
 * shelves and safety are states of ONE surface, so backing out of shelves never
 * lands back on the clarifying question.
 *
 * Restyled onto the studio's light design tokens (white canvas, black primary
 * hierarchy, brand red only as a supporting accent for entry points and
 * selected state). No genre rails, no browse grid — the empty state shows
 * queries, never shows.
 */

import { useEffect, useState } from 'react'

import { useMoodSearch } from '../../controllers/useMoodSearch'
import { Button } from '../primitives'
import { EmptyState, ErrorState } from '../StateViews'
import MoodEpisodeList from '../mood/MoodEpisodeList'
import MoodLab from '../mood/MoodLab'

/* ---------------------------------------------------------------- helpers -- */

function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

/* --------------------------------------------------------------- persona --- */

/**
 * Listener picker — a DEMO affordance, not a product surface. Real listeners
 * never choose who they are; in production this comes from auth. It sits inline
 * so you type once, switch listener, and watch the same query re-rank.
 */
function PersonaBar({ profiles, selected, onSelect }) {
  if (!profiles.length) return null

  const chip = (id, label, sub) => {
    const on = selected === id
    return (
      <button
        key={id ?? 'anon'}
        onClick={() => onSelect(id)}
        aria-pressed={on}
        style={{
          flex: '0 0 auto',
          textAlign: 'left',
          background: on ? 'var(--surface)' : 'transparent',
          border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-pill)',
          color: on ? 'var(--accent-text-sm)' : 'var(--muted)',
          padding: '8px 14px',
          fontSize: 13,
          fontFamily: 'var(--font-sans)',
          lineHeight: 1.2,
          cursor: 'pointer',
        }}
      >
        <div style={{ fontWeight: on ? 600 : 500 }}>{label}</div>
        {sub && <div style={{ fontSize: 11, opacity: 0.8, marginTop: 1 }}>{sub}</div>}
      </button>
    )
  }

  return (
    <div style={{ marginBottom: 24 }}>
      <SectionLabel style={{ marginBottom: 10 }}>Listening as</SectionLabel>
      <div style={{ display: 'flex', gap: 8, overflowX: 'auto', paddingBottom: 4 }}>
        {chip(null, 'Anyone', 'no history')}
        {profiles.map((p) =>
          chip(p.persona_id, p.display_name, `${p.slot} · ${p.history_count} watched`),
        )}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- starters -- */

function Starters({ starters, onPick }) {
  return (
    <div>
      <p style={{ margin: '0 0 18px', fontSize: 14, color: 'var(--muted)', maxWidth: 560 }}>
        No genres, no browse grid — just tell it how you want to feel. Or start with one of
        these.
      </p>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 12,
        }}
      >
        {starters.map((s) => (
          <button
            key={s.id}
            onClick={() => onPick(s.text)}
            style={{
              textAlign: 'left',
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--ink)',
              padding: '14px 16px',
              fontSize: 14.5,
              fontFamily: 'var(--font-sans)',
              lineHeight: 1.5,
              cursor: 'pointer',
            }}
          >
            {s.text}
          </button>
        ))}
      </div>
    </div>
  )
}

/* --------------------------------------------------------------- clarify --- */

function Clarify({ question, onAnswer }) {
  return (
    <div style={{ maxWidth: 560 }}>
      <p style={{ fontSize: 20, color: 'var(--ink)', margin: '0 0 22px', lineHeight: 1.4 }}>
        {question.question}
      </p>
      <div style={{ display: 'grid', gap: 10 }}>
        {question.options.map((o) => (
          <button
            key={o.id}
            onClick={() => onAnswer(o.id)}
            style={{
              textAlign: 'left',
              background: 'var(--surface-raised)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--ink)',
              padding: '14px 16px',
              fontSize: 15,
              fontFamily: 'var(--font-sans)',
              cursor: 'pointer',
            }}
          >
            {o.label}
          </button>
        ))}
      </div>
      <button
        onClick={() => onAnswer(null)}
        style={{
          marginTop: 16,
          background: 'none',
          border: 'none',
          color: 'var(--muted)',
          fontSize: 14,
          fontFamily: 'var(--font-sans)',
          cursor: 'pointer',
        }}
      >
        {question.skip_label}
      </button>
    </div>
  )
}

/* ---------------------------------------------------------------- shelves -- */

function RefineRow({ shelf, sliders, onRefine }) {
  if (!sliders.length) return null
  return (
    <div style={{ marginTop: 14, display: 'grid', gap: 8 }}>
      <SectionLabel>Refine in mood space</SectionLabel>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {sliders.map((s) => (
          <div key={s.id} style={{ display: 'flex', gap: 4 }}>
            {[
              [-1, s.left],
              [1, s.right],
            ].map(([v, label]) => (
              <button
                key={label}
                onClick={() => onRefine(shelf, { [s.id]: v })}
                aria-label={`${label}`}
                style={{
                  whiteSpace: 'nowrap',
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-pill)',
                  color: 'var(--muted)',
                  fontSize: 12.5,
                  fontFamily: 'var(--font-sans)',
                  padding: '6px 12px',
                  cursor: 'pointer',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function ResultCard({ result, onOpen }) {
  return (
    <article
      onClick={() => onOpen(result)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onOpen(result)}
      style={{
        background: 'var(--surface-raised)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '14px 16px',
        cursor: 'pointer',
      }}
    >
      {/* No provenance badge here on purpose. `audio_verified` is set by a
          coin flip in the seed fixture and hardcoded False by the real ingest
          path, so a "Tier A" chip would claim an audio pipeline that does not
          exist in this repo. Re-add it only once something actually verifies
          audio. */}
      <div style={{ fontSize: 15.5, color: 'var(--ink)', fontWeight: 600 }}>
        {result.series_title}
      </div>
      <div style={{ fontSize: 13, color: 'var(--accent-text-sm)', fontWeight: 600, marginTop: 4 }}>
        {result.entry_label}
      </div>
      {/* The line people quote. Give it room. */}
      <p style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.55, margin: '10px 0 0' }}>
        {result.explanation}
      </p>
    </article>
  )
}

function Shelves({ shelves, sliders, onRefine, onOpen }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 28,
        alignItems: 'start',
      }}
    >
      {shelves.map((shelf) => (
        <section key={shelf.id}>
          <header style={{ marginBottom: 14 }}>
            <h3 style={{ fontSize: 17, color: 'var(--ink)', margin: 0 }}>{shelf.label}</h3>
            <p style={{ fontSize: 13.5, color: 'var(--muted)', margin: '4px 0 0' }}>
              {shelf.subtitle}
            </p>
          </header>
          <div style={{ display: 'grid', gap: 10 }}>
            {shelf.results.map((r) => (
              <ResultCard key={r.content_id} result={r} onOpen={onOpen} />
            ))}
          </div>
          <RefineRow shelf={shelf} sliders={sliders} onRefine={onRefine} />
        </section>
      ))}
    </div>
  )
}

/* ---------------------------------------------------------------- safety --- */

function Safety({ message, resources }) {
  return (
    <div
      style={{
        maxWidth: 560,
        borderLeft: '3px solid var(--accent)',
        paddingLeft: 20,
      }}
    >
      <p style={{ fontSize: 17, color: 'var(--ink)', lineHeight: 1.65, margin: 0 }}>{message}</p>
      <div style={{ marginTop: 20, display: 'grid', gap: 8 }}>
        {(resources || []).map((r) => (
          <div key={r} style={{ fontSize: 15, color: 'var(--ink)', fontWeight: 600 }}>
            {r}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------- shell --- */

function SearchBar({ initial, onSearch, loading }) {
  const [text, setText] = useState(initial || '')

  useEffect(() => {
    setText(initial || '')
  }, [initial])

  const submit = () => {
    if (text.trim()) onSearch(text)
  }

  return (
    <div style={{ display: 'flex', gap: 10, maxWidth: 620, marginBottom: 28 }}>
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && submit()}
        placeholder="How do you want this to feel?"
        aria-label="How do you want this to feel?"
        style={{
          flex: 1,
          background: 'var(--surface-raised)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-sm)',
          color: 'var(--ink)',
          padding: '12px 16px',
          fontSize: 16,
          fontFamily: 'var(--font-sans)',
          outline: 'none',
        }}
      />
      <Button variant="primary" onClick={submit} disabled={loading}>
        {loading ? 'Searching…' : 'Search'}
      </Button>
    </div>
  )
}

export default function MoodSearchTab() {
  const mood = useMoodSearch()
  const { state, view } = mood
  const { mode, data } = state

  if (view === 'playing') {
    return (
      <div style={{ paddingTop: 40 }}>
        <MoodEpisodeList playing={mood.playing} onBack={mood.backToFeel} />
      </div>
    )
  }

  if (view === 'lab') {
    return (
      <div style={{ paddingTop: 40 }}>
        <MoodLab queryId={mood.queryId} lastText={mood.lastText} onBack={mood.backToFeel} />
      </div>
    )
  }

  // The safety screen shows nothing else — no search bar, no demo controls.
  if (mode === 'safety') {
    return (
      <div style={{ paddingTop: 40 }}>
        <Safety message={data.safety_message} resources={data.support_resources} />
      </div>
    )
  }

  return (
    <div style={{ paddingTop: 40 }}>
      <SearchBar initial={mood.lastText} onSearch={mood.search} loading={mood.loading} />

      <PersonaBar profiles={mood.profiles} selected={mood.profileId} onSelect={mood.pickProfile} />

      {mood.error && <ErrorState message={mood.error} />}

      {mode === 'clarify' && (
        <Clarify question={data.clarifying_question} onAnswer={mood.answer} />
      )}

      {mode === 'shelves' && (
        <Shelves
          shelves={data.shelves}
          sliders={mood.sliders}
          onRefine={mood.refine}
          onOpen={mood.open}
        />
      )}

      {mode === 'empty' &&
        (mood.starters.length ? (
          <Starters starters={mood.starters} onPick={mood.search} />
        ) : (
          <EmptyState
            title="Mood-First Search"
            hint="Type how you want to feel — the results come back as felt experience, not genre."
          />
        ))}

      {mood.devMode && view === 'feel' && (
        <button
          onClick={mood.openLab}
          style={{
            marginTop: 36,
            background: 'none',
            border: 'none',
            color: 'var(--muted)',
            fontSize: 13,
            fontFamily: 'var(--font-sans)',
            cursor: 'pointer',
          }}
        >
          Open Lab — genre baseline & retrieval trace ↗
        </button>
      )}
    </div>
  )
}
