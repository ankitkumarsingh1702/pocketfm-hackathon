import { useState } from 'react'
import { writersRoom } from './lib/api'

// A short Hindi-English horror-thriller Episode 7 excerpt, deliberately written
// with a saggy middle (repetitive corridor/room/stairs beats) and a soft,
// tension-free ending — so the room has something real to react to.
const SAMPLE_SCRIPT = `Raat ke teen baje, Meera purani haveli ke darwaze ke saamne khadi thi. Andar se ek dheemi si aawaz aa rahi thi — koi bacchi ro rahi thi. Usne kaanpte haathon se darwaza dhakela aur andar chali gayi.

Andar bahut andhera tha. Meera corridor mein aage badhi. Ek kamra tha, phir doosra kamra, phir teesra. Har kamre mein sirf dhool aur khaali kursiyan. Woh chalti rahi, chalti rahi. Usne socha shayad aawaz upar se aa rahi hai. Woh seedhiyan chadhne lagi. Seedhiyan lambi thi. Woh chadhti rahi, chadhti rahi.

Upar ek darwaza tha. Usne darwaza khola. Andar ek bacchi baithi thi. Bacchi mudi aur dheere se muskurayi. "Aap aa gaye," woh boli. Meera ko thoda ajeeb laga. Phir woh chup-chaap ghar wapas chali gayi.`

const VOICES = [
  { role: 'Director', blurb: 'Pacing, tension, and how each beat plays on the ear.' },
  { role: 'Editor', blurb: 'Structure, clarity, and where the middle sags.' },
  { role: 'Critic', blurb: 'Originality and whether the payoff earns its place.' },
  { role: 'Psychologist', blurb: 'Character motivation and emotional truth.' },
  { role: 'Historian', blurb: 'Genre lineage, tropes, and cultural resonance.' },
  { role: 'The Audience', blurb: 'Simulated listeners — do they keep pressing play?' },
]

const VERDICT_LABEL = { strong: 'Strong', mixed: 'Mixed', weak: 'Weak' }

// Clamp any number into a 0-100 range for meter widths.
function pct(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}

// Engagement can arrive on a few scales (0-1, 0-10, or 0-100). Normalise to a
// 0-100 meter width while keeping the original number for the label.
function engagementWidth(value) {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  if (n <= 1) return pct(n * 100)
  if (n <= 10) return pct(n * 10)
  return pct(n)
}

function formatNumber(value, digits = 0) {
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toFixed(digits)
}

function Meter({ label, valueText, width, tone = 'accent' }) {
  return (
    <div className="meter">
      <div className="meter-head">
        <span className="meter-label">{label}</span>
        <span className="meter-value">{valueText}</span>
      </div>
      <div className="meter-track" role="progressbar" aria-valuenow={Math.round(width)} aria-valuemin={0} aria-valuemax={100}>
        <div className={`meter-fill meter-fill--${tone}`} style={{ width: `${width}%` }} />
      </div>
    </div>
  )
}

function AudiencePanel({ audience }) {
  if (!audience) return null
  const following = pct(audience.following_pct)
  const engWidth = engagementWidth(audience.avg_engagement)

  return (
    <section className="audience-card" aria-labelledby="audience-heading">
      <div className="audience-card__glow" aria-hidden="true" />
      <div className="audience-card__body">
        <div className="audience-card__title">
          <span className="badge-star" aria-hidden="true">★</span>
          <h2 id="audience-heading">The Audience</h2>
          <span className="audience-card__tag">simulated listeners</span>
        </div>

        <div className="audience-meters">
          <Meter
            label="Still following"
            valueText={`${formatNumber(audience.following_pct, 0)}%`}
            width={following}
            tone="accent"
          />
          <Meter
            label="Avg. engagement"
            valueText={formatNumber(audience.avg_engagement, 1)}
            width={engWidth}
            tone="warm"
          />
        </div>

        {audience.comprehension && (
          <p className="audience-comprehension">{audience.comprehension}</p>
        )}

        {audience.confusion_points?.length > 0 && (
          <div className="audience-block">
            <h3 className="audience-block__label">Where they got lost</h3>
            <div className="chip-row">
              {audience.confusion_points.map((point, i) => (
                <span className="chip" key={i}>{point}</span>
              ))}
            </div>
          </div>
        )}

        {audience.representative_quotes?.length > 0 && (
          <div className="audience-block">
            <h3 className="audience-block__label">In their words</h3>
            <ul className="quote-list">
              {audience.representative_quotes.map((quote, i) => (
                <li className="quote" key={i}>“{quote}”</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}

function ExpertCard({ feedback }) {
  const { persona, role, note } = feedback
  const verdict = note?.verdict || 'mixed'
  const score = pct(note?.score)

  return (
    <article className={`expert-card expert-card--${verdict}`}>
      <header className="expert-card__head">
        <div className="expert-card__id">
          <h3 className="expert-card__role">{role}</h3>
          <p className="expert-card__persona">{persona}</p>
        </div>
        <span className={`verdict verdict--${verdict}`}>{VERDICT_LABEL[verdict] || verdict}</span>
      </header>

      <div className="score">
        <div className="score__head">
          <span className="score__label">Score</span>
          <span className="score__value">{formatNumber(note?.score, 0)}<span className="score__max">/100</span></span>
        </div>
        <div className="score__track">
          <div className={`score__fill score__fill--${verdict}`} style={{ width: `${score}%` }} />
        </div>
      </div>

      {note?.strengths?.length > 0 && (
        <div className="expert-card__section">
          <h4 className="expert-card__label expert-card__label--good">Strengths</h4>
          <ul className="bullets bullets--good">
            {note.strengths.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      {note?.issues?.length > 0 && (
        <div className="expert-card__section">
          <h4 className="expert-card__label expert-card__label--warn">Issues</h4>
          <ul className="bullets bullets--warn">
            {note.issues.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
      )}

      {note?.fix_suggestion && (
        <div className="fix">
          <span className="fix__label">Fix</span>
          <p className="fix__text">{note.fix_suggestion}</p>
        </div>
      )}
    </article>
  )
}

function EmptyState() {
  return (
    <section className="empty">
      <p className="empty__lead">
        Paste an episode, then convene the room. Six voices weigh in at once —
        five expert lenses and a simulated audience.
      </p>
      <div className="voices">
        {VOICES.map((v) => (
          <div className="voice" key={v.role}>
            <span className="voice__role">{v.role}</span>
            <span className="voice__blurb">{v.blurb}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function WritersRoom() {
  const [title, setTitle] = useState('Andhera')
  const [episode, setEpisode] = useState('7')
  const [text, setText] = useState(SAMPLE_SCRIPT)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  async function convene() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await writersRoom({ title, episode, text })
      setResult(data)
    } catch (err) {
      setError(err?.message || 'Something went wrong reaching the studio.')
    } finally {
      setLoading(false)
    }
  }

  const canRun = text.trim().length > 0 && !loading

  return (
    <div className="wr">
      <header className="wr-header">
        <div className="wr-header__inner">
          <div className="wr-brand">
            <span className="wr-brand__mark" aria-hidden="true">◐</span>
            <div>
              <h1 className="wr-brand__title">Simulated Studio</h1>
              <p className="wr-brand__subtitle">
                AI Writers Room — your experts and your audience, in one room.
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="wr-main">
        <section className="composer" aria-label="Script input">
          <div className="composer__meta">
            <label className="field">
              <span className="field__label">Title</span>
              <input
                className="field__input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Story title"
              />
            </label>
            <label className="field field--sm">
              <span className="field__label">Episode</span>
              <input
                className="field__input"
                value={episode}
                onChange={(e) => setEpisode(e.target.value)}
                placeholder="e.g. 7"
              />
            </label>
          </div>

          <label className="field">
            <span className="field__label">Script excerpt</span>
            <textarea
              className="field__textarea"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={12}
              spellCheck={false}
              placeholder="Paste your episode script here…"
            />
          </label>

          <div className="composer__actions">
            <button className="btn-primary" onClick={convene} disabled={!canRun}>
              {loading ? 'Convening the room…' : 'Convene the Writers Room'}
            </button>
            {loading && (
              <span className="composer__hint">
                The pro model deliberates carefully — this usually takes 20–40 seconds.
              </span>
            )}
          </div>
        </section>

        {loading && (
          <section className="status status--loading" role="status" aria-live="polite">
            <div className="spinner" aria-hidden="true" />
            <div>
              <p className="status__title">The room is in session</p>
              <p className="status__sub">
                Gathering five expert lenses and polling the simulated audience…
              </p>
            </div>
          </section>
        )}

        {error && !loading && (
          <section className="status status--error" role="alert">
            <span className="status__icon" aria-hidden="true">!</span>
            <div>
              <p className="status__title">The room couldn’t convene</p>
              <p className="status__sub">{error}</p>
            </div>
          </section>
        )}

        {!loading && !error && !result && <EmptyState />}

        {result && !loading && (
          <div className="results">
            {result.consensus && (
              <section className="consensus">
                <span className="consensus__label">Consensus</span>
                <p className="consensus__text">{result.consensus}</p>
              </section>
            )}

            <AudiencePanel audience={result.audience} />

            {result.panel?.length > 0 && (
              <section aria-labelledby="panel-heading">
                <div className="section-head">
                  <h2 id="panel-heading" className="section-head__title">The Expert Panel</h2>
                  <span className="section-head__count">{result.panel.length} voices</span>
                </div>
                <div className="expert-grid">
                  {result.panel.map((feedback, i) => (
                    <ExpertCard feedback={feedback} key={`${feedback.role}-${i}`} />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </main>

      <footer className="wr-footer">
        <span>Simulated Studio · persona-simulation on Google Vertex AI</span>
      </footer>
    </div>
  )
}
