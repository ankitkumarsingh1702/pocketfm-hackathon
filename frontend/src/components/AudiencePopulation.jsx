import { AGE_BAND_OPTIONS, useAudiencePopulation } from '../controllers/useAudiencePopulation'
import { displayGenre } from '../lib/agents'
import { initialsFor } from '../utils/agentDirectory'
import AgentDetailDrawer from './AgentDetailDrawer'
import { Button } from './primitives'
import { EmptyState, ErrorState, LoadingState } from './StateViews'

const SELECT_STYLE = (filled) => ({
  appearance: 'none',
  WebkitAppearance: 'none',
  fontFamily: 'var(--font-sans)',
  fontSize: 13,
  fontWeight: 600,
  color: filled ? 'var(--ink)' : 'var(--muted)',
  background: 'var(--surface-raised)',
  border: `1px solid ${filled ? 'var(--accent-line)' : 'var(--border)'}`,
  borderRadius: 'var(--radius-sm)',
  padding: '8px 30px 8px 11px',
  minHeight: 40,
  cursor: 'pointer',
  boxSizing: 'border-box',
})

function Chevron() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }}
    >
      <path d="M6 9l6 6 6-6" stroke="var(--muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

/** A labelled native <select> filter driven by facet {value,count} options. */
function FacetSelect({ label, value, options, onChange, allLabel }) {
  return (
    <div style={{ position: 'relative', flex: '1 1 150px', minWidth: 130 }}>
      <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} style={SELECT_STYLE(!!value)}>
        <option value="">{allLabel}</option>
        {(options || []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.value} ({o.count})
          </option>
        ))}
      </select>
      <Chevron />
    </div>
  )
}

/** One audience-agent card in the population grid. */
function MemberCard({ member, onOpen }) {
  const meta = [member.city, member.age ? `${member.age}` : null, member.gender].filter(Boolean).join(' · ')
  const genres = (member.genres || []).slice(0, 3)
  return (
    <button
      type="button"
      onClick={onOpen}
      style={{
        textAlign: 'left',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        padding: 16,
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border)',
        background: 'var(--surface-raised)',
        cursor: 'pointer',
        font: 'inherit',
        minHeight: 44,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span
          aria-hidden="true"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 36,
            height: 36,
            flexShrink: 0,
            borderRadius: 'var(--radius-sm)',
            fontFamily: 'var(--font-mono)',
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--ink)',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
          }}
        >
          {initialsFor(member.name)}
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {member.name}
          </div>
          <div style={{ fontSize: 12, color: 'var(--accent-text-sm)', fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {member.segment}
          </div>
        </div>
      </div>

      {meta && <div style={{ fontSize: 12, color: 'var(--muted)' }}>{meta}</div>}

      {genres.length > 0 && (
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap' }}>
          {genres.map((g) => (
            <span
              key={g}
              style={{
                fontSize: 11,
                color: 'var(--muted)',
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-pill)',
                padding: '2px 8px',
              }}
            >
              {displayGenre(g)}
            </span>
          ))}
        </div>
      )}

      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: member.has_memory ? 'var(--accent-text-sm)' : 'var(--dim)', marginTop: 'auto' }}>
        <span style={{ width: 7, height: 7, borderRadius: '50%', background: member.has_memory ? 'var(--accent)' : 'var(--dim)', flexShrink: 0 }} />
        {member.has_memory ? `${member.memory_count} ${member.memory_count === 1 ? 'memory' : 'memories'}` : 'no memory yet'}
      </div>
    </button>
  )
}

const SENTIMENT_TONE = {
  love: 'var(--accent-text-sm)',
  like: 'var(--accent-text-sm)',
  neutral: 'var(--muted)',
  dislike: 'var(--muted)',
  hate: 'var(--muted)',
}

/** One remembered reaction (the agent's history), for the detail drawer. */
function ReactionItem({ r, i }) {
  const facts = [r.sentiment, r.engagement, r.hook_score != null ? `hook ${r.hook_score}` : null]
    .filter(Boolean)
    .join(' · ')
  return (
    <div
      key={i}
      style={{
        padding: '10px 12px',
        border: '1px solid var(--border)',
        borderLeft: '3px solid var(--accent)',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface)',
      }}
    >
      {r.post && (
        <div style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--ink)', marginBottom: 3 }}>{r.post}</div>
      )}
      {facts && (
        <div style={{ fontSize: 11.5, color: SENTIMENT_TONE[r.sentiment] || 'var(--muted)', fontWeight: 600, marginBottom: r.comment ? 4 : 0 }}>
          {facts}
        </div>
      )}
      {r.comment && (
        <div style={{ fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.5, fontStyle: 'italic' }}>
          “{r.comment}”
        </div>
      )}
    </div>
  )
}

/**
 * AudiencePopulation — the searchable, filterable, paginated grid of the 1000s
 * of stateful listener agents, plus the per-agent detail drawer (profile,
 * context, memory & history). Self-contained: owns its own data via
 * useAudiencePopulation, so the parent just drops it into the directory.
 */
export default function AudiencePopulation({ active = true }) {
  const pop = useAudiencePopulation(active)
  const {
    filters,
    setFilter,
    toggleGenre,
    resetFilters,
    members,
    total,
    loading,
    loaded,
    error,
    facets,
    offset,
    page,
    pageCount,
    pageSize,
    nextPage,
    prevPage,
    detail,
    selectedId,
    openMember,
    closeMember,
    liveReaction,
    askAgent,
    activeFilterCount,
  } = pop

  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + pageSize, total)

  const profile = detail.data?.profile
  const memory = detail.data?.memory || []

  return (
    <section aria-label="Audience agents" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="label-upper" style={{ fontSize: 11 }}>
          Audience agents{facets?.total ? ` · ${facets.total.toLocaleString()}` : ''}
        </div>
        <p style={{ margin: 0, fontSize: 13.5, color: 'var(--muted)', lineHeight: 1.55, maxWidth: 660 }}>
          The full population of stateful listener agents — each with its own profile, character
          memory, and a history of how it reacted to past posts. Search or filter, then open one to
          read everything it remembers.
        </p>
      </div>

      {/* Search + filters */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <input
          type="search"
          value={filters.q}
          onChange={(e) => setFilter({ q: e.target.value })}
          placeholder="Search agents by name, segment or city…"
          aria-label="Search agents"
          style={{
            fontFamily: 'var(--font-sans)',
            fontSize: 14,
            color: 'var(--ink)',
            background: 'var(--surface-raised)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            padding: '11px 14px',
            width: '100%',
            boxSizing: 'border-box',
            minHeight: 44,
          }}
        />
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <FacetSelect label="Segment" value={filters.segment} options={facets?.segments} onChange={(v) => setFilter({ segment: v })} allLabel="All segments" />
          <FacetSelect label="City" value={filters.city} options={facets?.cities} onChange={(v) => setFilter({ city: v })} allLabel="All cities" />
          <FacetSelect label="Gender" value={filters.gender} options={facets?.genders} onChange={(v) => setFilter({ gender: v })} allLabel="Any gender" />
          <div style={{ position: 'relative', flex: '1 1 130px', minWidth: 120 }}>
            <select aria-label="Age band" value={filters.ageBand} onChange={(e) => setFilter({ ageBand: e.target.value })} style={SELECT_STYLE(!!filters.ageBand)}>
              <option value="">Any age</option>
              {AGE_BAND_OPTIONS.map((b) => (
                <option key={b} value={b}>{b}</option>
              ))}
            </select>
            <Chevron />
          </div>
          <div style={{ position: 'relative', flex: '1 1 150px', minWidth: 130 }}>
            <select
              aria-label="Memory"
              value={filters.hasMemory == null ? '' : filters.hasMemory ? 'yes' : 'no'}
              onChange={(e) => setFilter({ hasMemory: e.target.value === '' ? null : e.target.value === 'yes' })}
              style={SELECT_STYLE(filters.hasMemory != null)}
            >
              <option value="">Any memory</option>
              <option value="yes">Has memory</option>
              <option value="no">No memory yet</option>
            </select>
            <Chevron />
          </div>
        </div>

        {/* Genre chips */}
        {facets?.genres?.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            {facets.genres.slice(0, 12).map((g) => {
              const on = filters.genres.includes(g.value)
              return (
                <button
                  key={g.value}
                  type="button"
                  onClick={() => toggleGenre(g.value)}
                  aria-pressed={on}
                  style={{
                    fontSize: 11.5,
                    fontWeight: 600,
                    color: on ? 'var(--accent-text-sm)' : 'var(--muted)',
                    background: on ? 'var(--accent-soft)' : 'var(--surface-raised)',
                    border: `1px solid ${on ? 'var(--accent-line)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-pill)',
                    padding: '5px 11px',
                    cursor: 'pointer',
                    font: 'inherit',
                  }}
                >
                  {displayGenre(g.value)}
                </button>
              )
            })}
          </div>
        )}

        {/* Result count + reset */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12.5, color: 'var(--muted)' }} aria-live="polite">
            {loading && !loaded ? 'Loading agents…' : `Showing ${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()} agent${total === 1 ? '' : 's'}`}
          </span>
          {activeFilterCount > 0 && (
            <button
              type="button"
              onClick={resetFilters}
              style={{
                background: 'none',
                border: 'none',
                padding: 0,
                cursor: 'pointer',
                font: 'inherit',
                fontSize: 12.5,
                color: 'var(--accent-text-sm)',
                fontWeight: 600,
                textDecoration: 'underline',
              }}
            >
              Clear {activeFilterCount} filter{activeFilterCount === 1 ? '' : 's'}
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      {error && <ErrorState message={error} />}
      {!error && loading && !loaded && <LoadingState label="Loading the agent population…" />}
      {!error && loaded && total === 0 && (
        <EmptyState
          title="No agents match"
          hint={activeFilterCount > 0 ? 'Try clearing a filter or searching differently.' : 'Generate an audience in the Audience Simulator to populate the roster.'}
        />
      )}

      {members.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(min(220px, 100%), 1fr))',
            gap: 14,
            opacity: loading ? 0.6 : 1,
            transition: 'opacity var(--dur-fast, 150ms) var(--ease-standard, ease)',
          }}
        >
          {members.map((m) => (
            <MemberCard key={m.id} member={m} onOpen={() => openMember(m.id)} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {pageCount > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, justifyContent: 'center', paddingTop: 4 }}>
          <Button variant="secondary" size="sm" onClick={prevPage} disabled={offset === 0 || loading}>
            ← Prev
          </Button>
          <span style={{ fontSize: 12.5, color: 'var(--muted)' }}>
            Page {page + 1} of {pageCount.toLocaleString()}
          </span>
          <Button variant="secondary" size="sm" onClick={nextPage} disabled={to >= total || loading}>
            Next →
          </Button>
        </div>
      )}

      {/* Detail drawer */}
      {selectedId && (
        <AgentDetailDrawer
          key={selectedId}
          onClose={closeMember}
          name={profile?.name || 'Agent'}
          subtitle={profile?.segment || 'Audience listener'}
          badge="Audience agent"
          ask={{
            loading: liveReaction.loading,
            data: liveReaction.data,
            error: liveReaction.error,
            onAsk: askAgent,
          }}
          callInfo={{ agentId: selectedId }}
          facts={[
            { label: 'Segment', value: profile?.segment },
            { label: 'City', value: profile?.city },
            { label: 'Age', value: profile?.age },
            { label: 'Gender', value: profile?.gender },
            { label: 'Temperature', value: profile?.temperature != null ? Number(profile.temperature).toFixed(1) : null },
          ]}
          chipGroups={[
            { label: 'Genres', items: (profile?.genres || []).map(displayGenre) },
            { label: 'Traits', items: profile?.traits || [] },
          ]}
          systemPrompt={profile?.system_prompt}
          history={{
            title: 'Memory · past reactions',
            count: detail.data?.memory_count,
            loading: detail.loading,
            error: detail.error,
            empty: 'This agent has not reacted to any post yet — it has no memory to recall.',
            items: memory.map((r, i) => <ReactionItem key={i} r={r} i={i} />),
          }}
        />
      )}
    </section>
  )
}
