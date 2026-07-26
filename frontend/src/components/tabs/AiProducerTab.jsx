import { useState } from 'react'

import { HINDI_STORY_LIBRARY } from '../../config/hindiStories'
import { STORY_LIBRARY } from '../../config/storyLibrary'
import { useAiProducer } from '../../controllers/useAiProducer'
import StoryPicker from '../StoryPicker'
import { AgentLogConsole, Button, Icon, Pill, SurfaceCard } from '../primitives'
import { EmptyState, ErrorState } from '../StateViews'

const LANGS = [
  { id: 'en', label: 'English', code: 'en-IN', stories: STORY_LIBRARY },
  { id: 'hi', label: 'हिन्दी', code: 'hi-IN', stories: HINDI_STORY_LIBRARY },
]

/**
 * AI Producer lens — self-contained (its own composer, live feed, results).
 *
 * Pick a library show, and four Sarvam agents produce it: the Voice Casting
 * Director casts each character to a Sarvam voice you can *play*, the Sound
 * Designer scores the soundscape, the Pacing Editor maps tempo, and the Marketing
 * Strategist plans the launch. The run streams into an AgentLogConsole and each
 * card fills in as its agent lands.
 */
export default function AiProducerTab() {
  const { data, running, error, log, progress, run, stop, audio } = useAiProducer()
  const [langId, setLangId] = useState('en')
  const [selected, setSelected] = useState(null)

  const lang = LANGS.find((l) => l.id === langId) || LANGS[0]
  const hasLog = Array.isArray(log) && log.length > 0

  const onRun = () => {
    if (!selected || running) return
    run({ title: selected.title, episode: selected.episode, text: selected.text }, lang.code)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28, paddingTop: 8 }}>
      {/* Composer: language + a ready-made show + Run. */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span className="label-upper" style={{ fontSize: 10, color: 'var(--muted)' }}>
            Language
          </span>
          <div role="group" aria-label="Story language" style={styles.segment}>
            {LANGS.map((l) => {
              const active = l.id === langId
              return (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => {
                    setLangId(l.id)
                    setSelected(null)
                  }}
                  aria-pressed={active}
                  style={{ ...styles.segBtn, ...(active ? styles.segBtnOn : null) }}
                >
                  {l.label}
                </button>
              )
            })}
          </div>
        </div>

        <StoryPicker
          key={langId}
          stories={lang.stories}
          onSelect={(s) => setSelected(s)}
          label="Pick a show to produce"
          hint="Choose a show — the four agents produce that episode."
        />

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <Button variant="primary" onClick={onRun} disabled={!selected || running}>
            <Icon name="sparkles" size={18} />
            {running ? 'Producing…' : 'Produce this episode'}
          </Button>
          {!selected && (
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>
              Pick a show above to begin.
            </span>
          )}
        </div>
      </div>

      {/* Nothing run yet. */}
      {!running && !hasLog && !data && !error && (
        <EmptyState
          title="No production plan yet"
          hint="Pick a show and the AI Producer's four agents will cast the voices (which you can hear), design the sound, map the pacing, and plan the launch — live, as each agent lands."
        />
      )}

      {data && <PlanView data={data} audio={audio} />}

      {(running || hasLog) && (
        <AgentLogConsole
          log={log}
          running={running}
          progress={progress}
          onStop={stop}
          title="Producer agents"
          defaultOpen
        />
      )}

      {error && !running && <ErrorState message={error} />}
    </div>
  )
}

/** The combined production plan — memo banner + the four agents' cards. */
function PlanView({ data, audio }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {data.summary && (
        <div style={styles.memo}>
          <span className="label-upper" style={{ fontSize: 10, color: 'var(--accent-text-sm)' }}>
            Producer’s memo
          </span>
          <p style={{ margin: '6px 0 0', fontSize: 15, lineHeight: 1.6, color: 'var(--ink)' }}>
            {data.summary}
          </p>
        </div>
      )}

      <CastingCard casting={data.casting} audio={audio} />

      <div style={styles.grid}>
        <SoundCard sound={data.sound} />
        <PacingCard pacing={data.pacing} />
        <MarketingCard marketing={data.marketing} />
      </div>
    </div>
  )
}

function CardShell({ title, children, empty }) {
  return (
    <SurfaceCard>
      <div className="label-upper" style={{ fontSize: 11, marginBottom: 16 }}>
        {title}
      </div>
      {empty ? <p style={styles.dim}>{empty}</p> : children}
    </SurfaceCard>
  )
}

function CastingCard({ casting, audio }) {
  const chars = casting?.characters || []
  return (
    <SurfaceCard elevated>
      <div
        className="label-upper"
        style={{ fontSize: 11, marginBottom: 16, display: 'flex', gap: 10, alignItems: 'center' }}
      >
        <Icon name="volume" size={14} /> Voice Casting
      </div>
      {!casting ? (
        <p style={styles.dim}>Casting the voices…</p>
      ) : chars.length === 0 ? (
        <p style={styles.dim}>No speaking characters found.</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {chars.map((c, i) => {
            const key = `char:${i}`
            const isPlaying = audio.playingKey === key
            return (
              <div key={key} style={styles.voiceRow}>
                <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <strong style={{ fontSize: 14, color: 'var(--ink)' }}>{c.name}</strong>
                    {c.voice && <Pill label={c.voice} />}
                  </div>
                  {c.persona && <div style={styles.sub}>{c.persona}</div>}
                  {c.sample_line && (
                    <p style={styles.quote}>&ldquo;{c.sample_line}&rdquo;</p>
                  )}
                  {c.rationale && <div style={styles.dimSm}>{c.rationale}</div>}
                </div>
                <div style={{ flexShrink: 0 }}>
                  {c.audio_base64 ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => audio.play(key, c.audio_base64, c.mime)}
                    >
                      <Icon name={isPlaying ? 'pause' : 'play'} size={14} />
                      {isPlaying ? 'Stop' : 'Play voice'}
                    </Button>
                  ) : (
                    <span style={styles.dimSm}>no audio</span>
                  )}
                </div>
              </div>
            )
          })}
          {casting.narrator_note && (
            <div style={styles.narrator}>
              <span className="label-upper" style={{ fontSize: 10, color: 'var(--muted)' }}>
                Narrator
              </span>{' '}
              {casting.narrator_note}
            </div>
          )}
        </div>
      )}
    </SurfaceCard>
  )
}

function SoundCard({ sound }) {
  const cues = sound?.cues || []
  return (
    <CardShell title="Sound Design" empty={!sound ? 'Designing the soundscape…' : null}>
      {sound && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {sound.ambience && <p style={styles.lead}>{sound.ambience}</p>}
          {cues.map((cue, i) => (
            <div key={i} style={styles.cue}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <strong style={styles.cueScene}>{cue.scene}</strong>
                {cue.mood && <Pill label={cue.mood} />}
              </div>
              <div style={styles.sub}>{cue.cue}</div>
              {cue.timing && <div style={styles.dimSm}>{cue.timing}</div>}
            </div>
          ))}
        </div>
      )}
    </CardShell>
  )
}

function PacingCard({ pacing }) {
  const beats = pacing?.beats || []
  return (
    <CardShell title="Pacing" empty={!pacing ? 'Mapping the tempo…' : null}>
      {pacing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {pacing.overall && <p style={styles.lead}>{pacing.overall}</p>}
          {pacing.runtime_estimate && (
            <div style={styles.dimSm}>Est. runtime · {pacing.runtime_estimate}</div>
          )}
          {beats.map((b, i) => (
            <div key={i} style={styles.cue}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <strong style={styles.cueScene}>{b.section}</strong>
                {b.tempo && <Pill label={b.tempo} />}
              </div>
              {b.note && <div style={styles.sub}>{b.note}</div>}
            </div>
          ))}
        </div>
      )}
    </CardShell>
  )
}

function MarketingCard({ marketing }) {
  return (
    <CardShell title="Marketing" empty={!marketing ? 'Planning the launch…' : null}>
      {marketing && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {marketing.logline && (
            <p style={{ ...styles.lead, fontStyle: 'italic' }}>&ldquo;{marketing.logline}&rdquo;</p>
          )}
          {marketing.target_audience && (
            <div style={styles.dimSm}>For · {marketing.target_audience}</div>
          )}
          <ChipList label="Titles" items={marketing.title_options} />
          <BulletList label="Hooks" items={marketing.hooks} />
          <ChipList label="Channels" items={marketing.channels} />
          {marketing.release_note && (
            <div style={styles.sub}>
              <span className="label-upper" style={{ fontSize: 10, color: 'var(--muted)' }}>
                Release
              </span>{' '}
              {marketing.release_note}
            </div>
          )}
        </div>
      )}
    </CardShell>
  )
}

function ChipList({ label, items }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {items.map((it, i) => (
          <Pill key={i} label={it} />
        ))}
      </div>
    </div>
  )
}

function BulletList({ label, items }) {
  if (!items || items.length === 0) return null
  return (
    <div>
      <div className="label-upper" style={{ fontSize: 10, color: 'var(--muted)', marginBottom: 6 }}>
        {label}
      </div>
      <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {items.map((it, i) => (
          <li key={i} style={{ fontSize: 13.5, lineHeight: 1.5, color: 'var(--ink)' }}>
            {it}
          </li>
        ))}
      </ul>
    </div>
  )
}

const styles = {
  segment: { display: 'inline-flex', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden' },
  segBtn: {
    appearance: 'none',
    border: 'none',
    background: 'var(--surface)',
    color: 'var(--muted)',
    fontFamily: 'var(--font-sans)',
    fontSize: 13,
    fontWeight: 600,
    padding: '8px 16px',
    minHeight: 40,
    cursor: 'pointer',
  },
  segBtnOn: { background: 'var(--ink)', color: 'var(--canvas, #fff)' },
  memo: {
    padding: '14px 16px',
    border: '1px solid var(--accent-line)',
    background: 'var(--accent-soft)',
    borderRadius: 'var(--radius-md)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: 24,
    alignItems: 'start',
  },
  voiceRow: {
    display: 'flex',
    gap: 14,
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: 14,
    borderBottom: '1px solid var(--border)',
    flexWrap: 'wrap',
  },
  quote: { margin: '6px 0 4px', fontSize: 14, lineHeight: 1.55, color: 'var(--ink)' },
  lead: { margin: 0, fontSize: 14.5, lineHeight: 1.6, color: 'var(--ink)' },
  cue: { display: 'flex', flexDirection: 'column', gap: 3 },
  cueScene: { fontSize: 13.5, color: 'var(--ink)' },
  sub: { fontSize: 13.5, lineHeight: 1.5, color: 'var(--ink)' },
  dim: { margin: 0, fontSize: 13.5, color: 'var(--muted)', fontStyle: 'italic' },
  dimSm: { fontSize: 12.5, lineHeight: 1.5, color: 'var(--muted)' },
  narrator: { fontSize: 13, color: 'var(--ink)', paddingTop: 4 },
}
