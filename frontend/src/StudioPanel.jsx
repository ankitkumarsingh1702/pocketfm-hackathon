import { useEffect, useState } from 'react'
import { health, simulateAudience } from './lib/api'

// Self-contained demo panel for the Audience Simulator lens.
// Inline styles only (no new deps) so it drops into any Vite/React app.

const PLACEHOLDER = {
  title: 'Andhera',
  episode: 'Episode 7',
  text: `The lift doors close before Meera can step out. The number panel dies, then
every button glows at once. A child's laugh crackles through the speaker — the
same laugh from the tape her brother left behind. "Seventh floor," a voice
says, though the building has six. The lift begins to climb.`,
}

// --- tiny inline style helpers --------------------------------------------
const card = {
  border: '1px solid var(--border)',
  borderRadius: 12,
  padding: 20,
  background: 'var(--social-bg)',
  textAlign: 'left',
}
const label = { display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text-h)', margin: '0 0 6px' }
const input = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '8px 10px',
  borderRadius: 8,
  border: '1px solid var(--border)',
  background: 'var(--bg)',
  color: 'var(--text-h)',
  font: 'inherit',
  fontSize: 14,
}
const btn = (disabled) => ({
  padding: '10px 18px',
  borderRadius: 8,
  border: '1px solid var(--accent-border)',
  background: disabled ? 'var(--code-bg)' : 'var(--accent)',
  color: disabled ? 'var(--text)' : '#fff',
  fontWeight: 600,
  fontSize: 15,
  cursor: disabled ? 'not-allowed' : 'pointer',
})
const stat = {
  flex: 1,
  minWidth: 140,
  border: '1px solid var(--border)',
  borderRadius: 10,
  padding: '14px 16px',
  background: 'var(--bg)',
}

function StatTile({ value, unit, name }) {
  return (
    <div style={stat}>
      <div style={{ fontSize: 30, fontWeight: 700, color: 'var(--text-h)', lineHeight: 1.1 }}>
        {value}
        <span style={{ fontSize: 16, color: 'var(--text)', marginLeft: 2 }}>{unit}</span>
      </div>
      <div style={{ fontSize: 13, color: 'var(--text)', marginTop: 4 }}>{name}</div>
    </div>
  )
}

export default function StudioPanel() {
  const [hp, setHp] = useState(null) // health payload
  const [hpErr, setHpErr] = useState(null)

  const [title, setTitle] = useState(PLACEHOLDER.title)
  const [episode, setEpisode] = useState(PLACEHOLDER.episode)
  const [text, setText] = useState(PLACEHOLDER.text)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    let alive = true
    health()
      .then((data) => alive && setHp(data))
      .catch((e) => alive && setHpErr(e.message))
    return () => {
      alive = false
    }
  }, [])

  async function onRun() {
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await simulateAudience({ title, episode, text })
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const online = !!hp
  const dotColor = online ? '#22c55e' : hpErr ? '#ef4444' : '#f59e0b'

  return (
    <section style={{ ...card, margin: '24px auto', maxWidth: 880, background: 'var(--bg)' }}>
      {/* Header + health -------------------------------------------------- */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ margin: 0 }}>Simulated Studio</h2>
          <p style={{ fontSize: 14, color: 'var(--text)', marginTop: 4 }}>
            One persona-simulation engine, many lenses. Lens: <strong>Audience Simulator</strong>.
          </p>
        </div>
        <div
          title={online ? 'Backend online' : hpErr || 'Checking backend…'}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            border: '1px solid var(--border)',
            borderRadius: 999,
            padding: '6px 12px',
            background: 'var(--social-bg)',
          }}
        >
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: dotColor, boxShadow: `0 0 8px ${dotColor}` }} />
          {online ? (
            <span>
              {hp.provider} · {hp.project} · {hp.location}
              {hp.firestore ? ' · Firestore' : ''}
            </span>
          ) : hpErr ? (
            <span>backend offline</span>
          ) : (
            <span>connecting…</span>
          )}
        </div>
      </div>

      {/* Inputs ----------------------------------------------------------- */}
      <div style={{ display: 'flex', gap: 12, marginTop: 20, flexWrap: 'wrap' }}>
        <div style={{ flex: 2, minWidth: 200 }}>
          <label style={label} htmlFor="ss-title">Title</label>
          <input id="ss-title" style={input} value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div style={{ flex: 1, minWidth: 140 }}>
          <label style={label} htmlFor="ss-ep">Episode</label>
          <input id="ss-ep" style={input} value={episode} onChange={(e) => setEpisode(e.target.value)} />
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <label style={label} htmlFor="ss-text">Episode script</label>
        <textarea
          id="ss-text"
          style={{ ...input, minHeight: 130, resize: 'vertical', fontFamily: 'var(--mono)', fontSize: 13, lineHeight: 1.5 }}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>

      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button type="button" style={btn(loading || !text.trim())} disabled={loading || !text.trim()} onClick={onRun}>
          {loading ? 'Simulating…' : 'Run Audience Simulation'}
        </button>
        {loading && <span style={{ fontSize: 13, color: 'var(--text)' }}>Fanning out listeners on Vertex AI…</span>}
      </div>

      {/* Error ------------------------------------------------------------ */}
      {error && (
        <div
          style={{
            marginTop: 16,
            padding: '12px 14px',
            borderRadius: 8,
            border: '1px solid #ef4444',
            background: 'rgba(239,68,68,0.1)',
            color: 'var(--text-h)',
            fontSize: 14,
          }}
        >
          <strong>Simulation failed:</strong> {error}
        </div>
      )}

      {/* Results ---------------------------------------------------------- */}
      {result && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <StatTile value={Math.round(result.binge_pct)} unit="%" name="Binge / will continue" />
            <StatTile value={Math.round(result.avg_hook_score)} unit="/100" name="Avg hook score" />
            <StatTile value={result.total} unit="" name="Listeners simulated" />
          </div>

          {/* Drop-off / survival curve */}
          <h3 style={{ fontSize: 16, color: 'var(--text-h)', margin: '24px 0 4px' }}>Retention across the episode</h3>
          <p style={{ fontSize: 13, color: 'var(--text)', margin: '0 0 12px' }}>
            Share of listeners still tuned in at each stage.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(result.stages || []).map((stage, i) => {
              const frac = (result.drop_off_curve && result.drop_off_curve[i]) || 0
              const pct = Math.round(frac * 100)
              return (
                <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ width: 92, fontSize: 13, color: 'var(--text)', textTransform: 'capitalize', textAlign: 'right' }}>{stage}</span>
                  <div style={{ flex: 1, height: 20, borderRadius: 6, background: 'var(--code-bg)', overflow: 'hidden' }}>
                    <div style={{ width: `${pct}%`, height: '100%', background: 'var(--accent)', transition: 'width .4s ease' }} />
                  </div>
                  <span style={{ width: 44, fontSize: 13, color: 'var(--text-h)', fontVariantNumeric: 'tabular-nums' }}>{pct}%</span>
                </div>
              )
            })}
          </div>

          {/* Segments table */}
          {result.segments && result.segments.length > 0 && (
            <>
              <h3 style={{ fontSize: 16, color: 'var(--text-h)', margin: '24px 0 12px' }}>By segment</h3>
              <div style={{ overflowX: 'auto', border: '1px solid var(--border)', borderRadius: 10 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ textAlign: 'left', color: 'var(--text)' }}>
                      <th style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>Segment</th>
                      <th style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', textAlign: 'right' }}>Listeners</th>
                      <th style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', textAlign: 'right' }}>Binge %</th>
                      <th style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', textAlign: 'right' }}>Avg hook</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.segments.map((s) => (
                      <tr key={s.segment}>
                        <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', color: 'var(--text-h)' }}>{s.segment}</td>
                        <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{s.count}</td>
                        <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{Math.round(s.binge_pct)}%</td>
                        <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{Math.round(s.avg_hook)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* Top churn reasons */}
          {result.top_churn_reasons && result.top_churn_reasons.length > 0 && (
            <>
              <h3 style={{ fontSize: 16, color: 'var(--text-h)', margin: '24px 0 8px' }}>Why listeners dropped</h3>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 14 }}>
                {result.top_churn_reasons.map((r, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>{r}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </section>
  )
}
