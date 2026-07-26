import { useRef } from 'react'

import AgentProfile from '../../AgentProfile'
import { audienceSummary } from '../../lib/agents'
import { useAudienceSim } from '../../controllers/useAudienceSim'
import { useCountUp } from '../../hooks/useCountUp'
import { formatInt } from '../../utils/format'
import {
  BarChart,
  Button,
  Disclosure,
  Icon,
  MetricNumber,
  QuoteCard,
  ScoreGauge,
  SurfaceCard,
} from '../primitives'
import { ErrorState } from '../StateViews'
import StoryPicker from '../StoryPicker'
// The agent-profile drawer + its form controls are styled by the Writers Room
// stylesheet (and its --ui-* token bridge). Import them so the drawer renders
// correctly when this lens is the first one opened.
import '../../ui-tokens.css'
import '../../writers-room.css'

const PANEL_SIZES = [50, 200, 500, 1000, 2000]

const SENTIMENT_LABEL = {
  love: 'Loved it',
  like: 'Liked it',
  neutral: 'Neutral',
  mixed: 'Mixed',
  dislike: 'Disliked',
}
const ENGAGEMENT_LABEL = {
  scroll_past: 'Scrolled past',
  like: 'Liked',
  comment: 'Commented',
  save: 'Saved',
  share: 'Shared',
  subscribe: 'Subscribed',
  binge: 'Binged',
}

function sentimentTone(sentiment) {
  if (sentiment === 'love' || sentiment === 'like') return 'positive'
  if (sentiment === 'dislike' || sentiment === 'mixed') return 'negative'
  return 'neutral'
}

function SectionLabel({ children, style }) {
  return (
    <div className="label-upper" style={{ fontSize: 11, ...style }}>
      {children}
    </div>
  )
}

/** Small text+colour badge (never colour alone — the word always shows). */
function Badge({ children, tone = 'neutral' }) {
  const tones = {
    positive: { color: 'var(--ink)', border: 'var(--border)', bg: 'var(--surface)' },
    negative: { color: 'var(--accent-text-sm)', border: 'var(--accent-line)', bg: 'var(--accent-soft)' },
    neutral: { color: 'var(--muted)', border: 'var(--border)', bg: 'var(--surface)' },
  }
  const s = tones[tone] || tones.neutral
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 12,
        fontWeight: 600,
        color: s.color,
        background: s.bg,
        border: `1px solid ${s.border}`,
        borderRadius: 'var(--radius-pill)',
        padding: '2px 10px',
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </span>
  )
}

/** One listener-agent's reaction, with a glass-box "why" disclosure. */
function ReactionCard({ r }) {
  const who = [r.name, r.city].filter(Boolean).join(' · ')
  const num = { fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }
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
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'baseline' }}>
        <span style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 14 }}>{who || 'Listener'}</span>
        <span style={{ ...num, fontSize: 13, color: 'var(--muted)' }}>hook {r.hook_score}</span>
      </div>
      {r.segment && <SectionLabel style={{ fontSize: 10 }}>{r.segment}</SectionLabel>}
      {r.comment && (
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: 'var(--ink)' }}>
          &ldquo;{r.comment}&rdquo;
        </p>
      )}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Badge tone={sentimentTone(r.sentiment)}>{SENTIMENT_LABEL[r.sentiment] || r.sentiment}</Badge>
        <Badge tone={r.engagement === 'scroll_past' ? 'neutral' : 'positive'}>
          {ENGAGEMENT_LABEL[r.engagement] || r.engagement}
        </Badge>
        {r.emotion && <Badge tone="neutral">{r.emotion}</Badge>}
      </div>
      {(r.reasoning || r.memory_note) && (
        <Disclosure summary={<span className="label-upper" style={{ fontSize: 10 }}>Why they reacted</span>}>
          <div style={{ paddingTop: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {r.reasoning && (
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: 'var(--muted)' }}>{r.reasoning}</p>
            )}
            {r.memory_note && (
              <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: 'var(--ink-subtle, var(--muted))', fontStyle: 'italic' }}>
                Memory: {r.memory_note}
              </p>
            )}
          </div>
        </Disclosure>
      )}
    </div>
  )
}

/** An editable audience-member chip; click to open its profile drawer. */
function RosterCard({ agent, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="cast-card"
      style={{
        textAlign: 'left',
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        padding: '12px 14px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        minHeight: 44,
      }}
    >
      <span style={{ fontWeight: 600, color: 'var(--ink)', fontSize: 14 }}>{agent.name}</span>
      {agent.segment && <SectionLabel style={{ fontSize: 10 }}>{agent.segment}</SectionLabel>}
      <span style={{ fontSize: 12, color: 'var(--muted)' }}>{audienceSummary(agent)}</span>
    </button>
  )
}

const barsFrom = (rows, labels) =>
  (rows || [])
    .filter((row) => row.count > 0)
    .map((row) => ({ label: labels[row.sentiment || row.action] || row.sentiment || row.action, value: Math.round(row.pct) }))

function Dashboard({ result }) {
  const listen = useCountUp(result.listen_pct, true)
  const num = { fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }
  const sentimentBars = barsFrom(result.sentiment_breakdown, SENTIMENT_LABEL)
  const engagementBars = barsFrom(result.engagement_funnel, ENGAGEMENT_LABEL)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 48 }}>
      <div style={{ display: 'flex', gap: 40, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <MetricNumber value={listen} suffix="%" size="hero" tone="accent" />
          <SectionLabel style={{ marginTop: 8, fontSize: 12 }}>
            would hit play · across {formatInt(result.total)} agents
            {result.dropped > 0 ? ` · ${result.dropped} dropped` : ''}
          </SectionLabel>
        </div>
        <ScoreGauge score={Math.round(result.virality)} label="VIRALITY" size={140} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <MetricNumber value={result.avg_hook_score} size="lg" tone="ink" />
          <SectionLabel style={{ fontSize: 10 }}>Avg hook score</SectionLabel>
        </div>
      </div>

      {sentimentBars.length > 0 && (
        <div style={{ maxWidth: 640 }}>
          <SectionLabel style={{ marginBottom: 16 }}>Sentiment</SectionLabel>
          <BarChart data={sentimentBars} />
        </div>
      )}

      {engagementBars.length > 0 && (
        <div style={{ maxWidth: 640 }}>
          <SectionLabel style={{ marginBottom: 16 }}>What they'd do</SectionLabel>
          <BarChart data={engagementBars} />
        </div>
      )}

      {result.segments?.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 16 }}>By segment</SectionLabel>
          <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
              <thead>
                <tr style={{ textAlign: 'left', color: 'var(--muted)' }}>
                  <th style={cellHead}>Segment</th>
                  <th style={{ ...cellHead, textAlign: 'right' }}>Agents</th>
                  <th style={{ ...cellHead, textAlign: 'right' }}>Positive&nbsp;%</th>
                  <th style={{ ...cellHead, textAlign: 'right' }}>Play&nbsp;%</th>
                  <th style={{ ...cellHead, textAlign: 'right' }}>Avg&nbsp;hook</th>
                </tr>
              </thead>
              <tbody>
                {result.segments.map((s) => (
                  <tr key={s.segment}>
                    <td style={{ ...cell, color: 'var(--ink)' }}>{s.segment}</td>
                    <td style={{ ...cell, textAlign: 'right', ...num }}>{formatInt(s.count)}</td>
                    <td style={{ ...cell, textAlign: 'right', ...num }}>{s.positive_pct}%</td>
                    <td style={{ ...cell, textAlign: 'right', ...num }}>{s.listen_pct}%</td>
                    <td style={{ ...cell, textAlign: 'right', ...num }}>{s.avg_hook}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {result.top_comments?.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 16 }}>Top comments</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            {result.top_comments.map((c) => (
              <QuoteCard key={c.persona_id} quote={c.comment} persona={[c.name, c.segment].filter(Boolean).join(' · ')} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

const cellHead = { padding: '10px 14px', borderBottom: '1px solid var(--border)', fontWeight: 600 }
const cell = { padding: '10px 14px', borderBottom: '1px solid var(--border)' }

const ROSTER_PREVIEW = 12

export default function AudienceSimulatorTab() {
  const sim = useAudienceSim()
  const fileRef = useRef(null)
  const sizeRef = useRef(null)

  const {
    library, roster, segments, activeAgent, openAgent, closeAgent, updateAgent,
    generate, generating, genError,
    post, setPostField, setImage, clearImage,
    run, stop, running, canRun, recent, progress, runMeta, result, error,
  } = sim

  const feed = result ? result.reactions : recent
  const pct = progress.total ? Math.round((progress.done / progress.total) * 100) : 0

  const onGenerate = () => {
    const n = Number(sizeRef.current?.value) || 200
    generate(n)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40, paddingTop: 8 }}>
      {/* Glass-box explainer */}
      <SurfaceCard style={{ padding: 'var(--space-5)' }}>
        <SectionLabel style={{ marginBottom: 8 }}>How the Living Audience works</SectionLabel>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--muted)' }}>
          Each listener is a real agent. It <strong style={{ color: 'var(--ink)' }}>sees your image</strong>,
          {' '}recalls how it reacted to your past posts from the shared knowledge graph, deliberates, then
          decides one thing to do — scroll past, like, comment, share, save, subscribe or binge. Edit any
          profile below and that listener&rsquo;s behaviour changes on the next run.
        </p>
      </SurfaceCard>

      {/* Composer */}
      <SurfaceCard>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <StoryPicker
            onSelect={(s) => {
              setPostField('title', s.title)
              setPostField('text', s.text)
            }}
            label="Load a ready-made story to test"
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

          {/* Image upload */}
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
            <span style={{ flex: 1 }} />
            {running ? (
              <Button variant="secondary" onClick={stop}>
                <Icon name="stop" size={16} /> Stop
              </Button>
            ) : (
              <Button variant="primary" onClick={run} disabled={!canRun}>
                <Icon name="play" size={16} /> Run {formatInt(roster.length)} agents
              </Button>
            )}
          </div>
        </div>
      </SurfaceCard>

      {/* Audience roster */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
          <SectionLabel>
            Your audience — {formatInt(roster.length)} members
            {library?.source ? ` · ${library.source}` : ''}
          </SectionLabel>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <select ref={sizeRef} defaultValue={200} style={{ ...inputStyle, padding: '8px 12px', minHeight: 36 }}>
              {PANEL_SIZES.map((n) => (
                <option key={n} value={n}>{formatInt(n)} listeners</option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={onGenerate} disabled={generating}>
              <Icon name="sparkles" size={16} />
              {generating ? 'Generating…' : 'Generate audience'}
            </Button>
          </div>
        </div>
        {genError && <div style={{ marginBottom: 12 }}><ErrorState message={genError} /></div>}
        {generating ? (
          <p style={{ margin: 0, fontSize: 14, color: 'var(--muted)' }}>
            Synthesising a diverse audience of distinct listeners…
          </p>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            {roster.slice(0, ROSTER_PREVIEW).map((agent) => (
              <RosterCard key={agent.id} agent={agent} onClick={() => openAgent(agent.id)} />
            ))}
            {roster.length > ROSTER_PREVIEW && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted)', fontSize: 13, border: '1px dashed var(--border)', borderRadius: 'var(--radius-md)', padding: 12 }}>
                +{formatInt(roster.length - ROSTER_PREVIEW)} more listeners in the panel
              </div>
            )}
          </div>
        )}
      </div>

      {error && <ErrorState message={error} />}

      {/* Live run progress */}
      {(running || (progress.total > 0 && !result)) && (
        <div>
          <SectionLabel style={{ marginBottom: 12 }}>
            {running ? 'Agents reacting live' : 'Run finished'}
          </SectionLabel>
          <ProgressWithCount pct={pct} progress={progress} runMeta={runMeta} />
        </div>
      )}

      {/* Aggregate dashboard */}
      {result && <Dashboard result={result} />}

      {/* Reaction feed */}
      {feed.length > 0 && (
        <div>
          <SectionLabel style={{ marginBottom: 16 }}>
            {result ? 'Reactions' : 'Live reactions'} · {formatInt(feed.length)} shown
          </SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
            {feed.map((r, i) => (
              <ReactionCard key={`${r.persona_id}-${i}`} r={r} />
            ))}
          </div>
        </div>
      )}

      {activeAgent && (
        <AgentProfile
          agent={activeAgent}
          segmentOptions={segments}
          onChange={updateAgent}
          onClose={closeAgent}
        />
      )}
    </div>
  )
}

function ProgressWithCount({ pct, progress, runMeta }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ height: 3, background: 'var(--grey-200)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: 'var(--accent)', borderRadius: 2, transition: 'width var(--dur-med) var(--ease-standard)' }} />
      </div>
      <span className="label-upper" style={{ fontSize: 12 }}>
        {formatInt(progress.done)} of {formatInt(progress.total)} agents reacted
        {progress.dropped > 0 ? ` · ${formatInt(progress.dropped)} dropped` : ''}
        {runMeta?.model ? ` · ${runMeta.model}` : ''}
        {runMeta?.hasImage ? ' · image-aware' : ''}
      </span>
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
