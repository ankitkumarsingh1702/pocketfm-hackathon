import { useMemo, useRef, useState } from 'react'

import { useA2ACascade } from '../../controllers/useA2ACascade'
import { buildGraphData, RING_LEGEND } from '../../utils/a2aCascade'
import { buildStorySoFar } from '../../lib/storySoFar'
import { formatInt } from '../../utils/format'
import {
  AgentLogConsole,
  Button,
  GraphCanvas,
  Icon,
  MetricNumber,
  ScoreGauge,
  SurfaceCard,
} from '../primitives'
import { ErrorState } from '../StateViews'
import StoryPicker from '../StoryPicker'
import ImagePicker from '../ImagePicker'
// The token bridge, in case this lens is the first one opened.
import '../../ui-tokens.css'

const SEED_SIZES = [12, 24, 40, 60]

function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

/** One A→B message: a spreader's actual comment reaching a follower. */
function MessageCard({ msg }) {
  const fromWho = [msg.from?.name, msg.from?.segment].filter(Boolean).join(' · ')
  const toWho = [msg.to?.name, msg.to?.segment].filter(Boolean).join(' · ')
  return (
    <div
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-5)',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 13.5 }}>{fromWho || 'A listener'}</span>
        <span style={{ color: 'var(--accent-text-sm)', display: 'inline-flex' }}>
          <Icon name="share" size={15} />
        </span>
        <span style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 13.5 }}>{toWho || 'a follower'}</span>
      </div>
      {(msg.comment || '').trim() ? (
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: 'var(--ink)' }}>
          &ldquo;{msg.comment}&rdquo;
        </p>
      ) : (
        <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)' }}>shared it onward.</p>
      )}
    </div>
  )
}

/** Reach per hop — raw counts (BarChart renders %, so this is a small custom bar). */
function ReachByHop({ curve }) {
  const max = Math.max(...curve, 1)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {curve.map((count, i) => (
        <div
          key={i}
          style={{ display: 'grid', gridTemplateColumns: '90px 1fr 44px', alignItems: 'center', gap: 12 }}
        >
          <span className="label-upper" style={{ fontSize: 11, textAlign: 'right' }}>
            {i === 0 ? 'Seed' : `Hop ${i}`}
          </span>
          <div style={{ background: 'var(--surface)', borderRadius: 4, height: 10, overflow: 'hidden' }}>
            <div
              style={{
                width: `${(count / max) * 100}%`,
                height: '100%',
                background: i === 0 ? 'var(--ink)' : 'var(--accent)',
                borderRadius: 4,
                transition: 'width var(--dur-slow) var(--ease-standard)',
              }}
            />
          </div>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              color: 'var(--muted)',
              fontWeight: 600,
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {formatInt(count)}
          </span>
        </div>
      ))}
    </div>
  )
}

export default function A2ATab() {
  const a2a = useA2ACascade()
  const fileRef = useRef(null)
  const [showComposer, setShowComposer] = useState(true)

  const {
    post, setPostField, setImage, clearImage,
    seedN, setSeedN, run, stop, running, canRun, state,
  } = a2a

  const { runMeta, result, progress, rounds, messages, log } = state

  const graphData = useMemo(
    () => buildGraphData(state.nodesById, state.edges),
    [state.nodesById, state.edges],
  )

  const population = runMeta?.population || result?.population || 0
  const reached = result?.total_reached ?? progress.reached
  const reachPct = population ? Math.min(100, Math.round((reached / population) * 100)) : 0
  const coefficient = result?.virality_coefficient
  const depth = result?.rounds ?? progress.rounds
  const seedCount = result?.seed_count ?? runMeta?.seed ?? seedN

  const curve = result?.reach_curve?.length ? result.reach_curve : rounds.map((r) => r.newReach)
  const featured = messages.filter((m) => (m.comment || '').trim()).slice(0, 6)
  const roundsPresent = new Set(Object.values(state.nodesById).map((n) => n.round))
  const hasRun = running || Boolean(result) || reached > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40, paddingTop: 8 }}>
      {/* Glass-box explainer */}
      <SurfaceCard style={{ padding: 'var(--space-5)' }}>
        <SectionLabel style={{ marginBottom: 8 }}>How agent-to-agent word of mouth works</SectionLabel>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--muted)' }}>
          Unlike the Audience Simulator — where every agent reacts on its own — here the agents
          {' '}<strong style={{ color: 'var(--ink)' }}>talk to each other</strong>. A small seed cohort
          sees the post first. When an agent <strong style={{ color: 'var(--ink)' }}>shares or subscribes</strong>,
          its <strong style={{ color: 'var(--ink)' }}>actual comment is passed to the peers who follow it</strong>
          {' '}— injected into their prompt as social proof — and the post spreads hop by hop through the
          knowledge-graph social network. Watch it cascade below.
        </p>
      </SurfaceCard>

      {/* Composer */}
      <SurfaceCard>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
            <SectionLabel>The post you seed into the network</SectionLabel>
            <button type="button" onClick={() => setShowComposer((v) => !v)} style={linkBtn}>
              {showComposer ? 'Hide' : 'Edit'}
            </button>
          </div>

          {showComposer && (
            <>
              <StoryPicker
                onSelect={(s) => {
                  setPostField('title', s.title)
                  setPostField('text', s.text)
                  setPostField('episode', s.episode || '')
                  setPostField('storySoFar', buildStorySoFar(s.episodes, s.episodeN))
                }}
                label="Load a ready-made story to seed"
              />
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <SectionLabel>Post title</SectionLabel>
                <input
                  type="text"
                  value={post.title}
                  onChange={(e) => setPostField('title', e.target.value)}
                  placeholder="Your episode / teaser headline"
                  style={inputStyle}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <SectionLabel>Post text</SectionLabel>
                <textarea
                  value={post.text}
                  onChange={(e) => setPostField('text', e.target.value)}
                  rows={4}
                  placeholder="What you're posting to your audience…"
                  style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5 }}
                />
              </label>

              <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  onChange={(e) => setImage(e.target.files?.[0])}
                  style={{ display: 'none' }}
                />
                <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
                  <Icon name="image" size={16} />
                  {post.image ? 'Change image' : 'Attach image'}
                </Button>
                <ImagePicker onSelect={(img) => setPostField('image', img)} title={post.title} />
                {post.image && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <img
                      src={post.image.dataUrl}
                      alt="Post preview"
                      style={{ height: 44, width: 44, objectFit: 'cover', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border)' }}
                    />
                    <button type="button" onClick={clearImage} style={linkBtn}>Remove</button>
                  </div>
                )}
              </div>
            </>
          )}

          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <SectionLabel style={{ margin: 0 }}>Seed cohort</SectionLabel>
              <select
                value={seedN}
                onChange={(e) => setSeedN(Number(e.target.value))}
                style={{ ...inputStyle, padding: '8px 12px', minHeight: 36, width: 'auto' }}
              >
                {SEED_SIZES.map((n) => (
                  <option key={n} value={n}>{n} agents</option>
                ))}
              </select>
            </label>
            <span style={{ flex: 1 }} />
            {running ? (
              <Button variant="secondary" onClick={stop}>
                <Icon name="stop" size={16} /> Stop
              </Button>
            ) : (
              <Button variant="primary" onClick={run} disabled={!canRun}>
                <Icon name="share" size={16} /> Seed &amp; spread
              </Button>
            )}
          </div>
        </div>
      </SurfaceCard>

      {state.error && <ErrorState message={state.error} />}

      {/* Metrics */}
      {hasRun && (
        <div style={{ display: 'flex', gap: 40, alignItems: 'center', flexWrap: 'wrap' }}>
          <div>
            <MetricNumber value={reached} size="hero" tone="accent" />
            <SectionLabel style={{ marginTop: 8, fontSize: 12 }}>
              agents reached · from {formatInt(seedCount)} seeds
            </SectionLabel>
          </div>
          <ScoreGauge score={reachPct} label="NETWORK REACHED" size={140} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={coefficient != null ? coefficient : 0} suffix="×" size="lg" tone="ink" />
            <SectionLabel style={{ fontSize: 10 }}>Virality (new reach / sharer)</SectionLabel>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <MetricNumber value={depth} size="lg" tone="ink" />
            <SectionLabel style={{ fontSize: 10 }}>Hops it travelled</SectionLabel>
          </div>
        </div>
      )}

      {/* Cascade graph — the money shot */}
      {hasRun && (
        <div>
          <SectionLabel style={{ marginBottom: 6 }}>The cascade</SectionLabel>
          <p style={{ margin: '0 0 14px', fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.55 }}>
            Centre = the seeded agents. Each ring outward is one word-of-mouth hop; a{' '}
            <strong style={{ color: 'var(--accent-text-sm)' }}>red line</strong> is one agent&rsquo;s comment
            reaching a follower. Hover any agent to trace its links.
          </p>
          {graphData.isEmpty ? (
            <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>Waiting for the first agents to react…</p>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 12 }}>
                {RING_LEGEND.filter((r) => roundsPresent.has(r.round) || (r.round === 4 && [...roundsPresent].some((x) => x >= 4))).map((r) => (
                  <span key={r.round} style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, color: 'var(--muted)' }}>
                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
                    {r.label}
                  </span>
                ))}
              </div>
              <SurfaceCard style={{ padding: 'var(--space-4)' }}>
                <GraphCanvas data={graphData} />
              </SurfaceCard>
            </>
          )}
        </div>
      )}

      {/* Live relay log — genuine agent-to-agent messages */}
      {hasRun && (
        <div>
          <SectionLabel style={{ marginBottom: 12 }}>Agent-to-agent relay</SectionLabel>
          <AgentLogConsole
            log={log}
            running={running}
            onStop={stop}
            title="Word-of-mouth relay"
            progress={{ label: 'reached', done: progress.reached, total: population }}
          />
        </div>
      )}

      {/* Featured A→B messages */}
      {featured.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 6 }}>What agents told each other</SectionLabel>
          <p style={{ margin: '0 0 16px', fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.55 }}>
            Each card is a real message: one agent&rsquo;s comment, passed to a follower who then decided
            for themselves.
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            {featured.map((m, i) => (
              <MessageCard key={`${m.from?.id}-${m.to?.id}-${i}`} msg={m} />
            ))}
          </div>
        </div>
      )}

      {/* Reach by hop + super-spreaders */}
      {curve.length > 0 && (
        <div style={{ display: 'flex', gap: 48, flexWrap: 'wrap' }}>
          <div style={{ flex: '1 1 320px', minWidth: 280 }}>
            <SectionLabel style={{ marginBottom: 16 }}>Reach by hop</SectionLabel>
            <ReachByHop curve={curve} />
          </div>
          {result?.super_spreaders?.length > 0 && (
            <div style={{ flex: '1 1 320px', minWidth: 280 }}>
              <SectionLabel style={{ marginBottom: 16 }}>Top super-spreaders</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {result.super_spreaders.map((s) => (
                  <div
                    key={s.id}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottom: '1px solid var(--border)', paddingBottom: 8 }}
                  >
                    <span style={{ fontSize: 14, color: 'var(--ink)' }}>
                      {s.name}
                      {s.segment ? <span style={{ color: 'var(--muted)' }}> · {s.segment}</span> : null}
                    </span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600, color: 'var(--accent-text-sm)', whiteSpace: 'nowrap' }}>
                      {formatInt(s.reached)} reached
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const inputStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 15,
  color: 'var(--ink)',
  background: 'var(--canvas, #fff)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-sm)',
  padding: '10px 12px',
  width: '100%',
  boxSizing: 'border-box',
}

const linkBtn = {
  background: 'none',
  border: 'none',
  color: 'var(--accent-text-sm)',
  fontSize: 13,
  fontWeight: 600,
  cursor: 'pointer',
  padding: 0,
}
