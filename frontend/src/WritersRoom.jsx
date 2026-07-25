import { useEffect, useMemo, useRef, useState } from 'react'
import './ui-tokens.css'
import './writers-room.css'
import { getPersonas, writersRoomStream } from './lib/api'
import AgentProfile from './AgentProfile'
import { useStatusToast } from './hooks/useStatusToast'
import { useToast } from './components/toast/useToast'
import { audienceSummary, cloneAgent, expertSummary, segmentOptions } from './lib/agents'

// A short Hindi-English horror-thriller Episode 7 excerpt, deliberately written
// with a saggy middle (repetitive corridor/room/stairs beats) and a soft,
// tension-free ending — so the room has something real to react to. (~120 words)
const SAMPLE_SCRIPT = `Raat ke teen baje, Meera purani haveli ke darwaze ke saamne khadi thi. Andar se ek dheemi si aawaz aa rahi thi — koi bacchi ro rahi thi. Usne kaanpte haathon se darwaza dhakela aur andar chali gayi.

Andar bahut andhera tha. Meera corridor mein aage badhi. Ek kamra tha, phir doosra kamra, phir teesra. Har kamre mein sirf dhool aur khaali kursiyan. Woh chalti rahi, chalti rahi. Usne socha shayad aawaz upar se aa rahi hai. Woh seedhiyan chadhne lagi. Seedhiyan lambi thi. Woh chadhti rahi, chadhti rahi.

Upar ek darwaza tha. Usne darwaza khola. Andar ek bacchi baithi thi. Bacchi mudi aur dheere se muskurayi. "Aap aa gaye," woh boli. Meera ko thoda ajeeb laga. Phir woh chup-chaap ghar wapas chali gayi.`

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

function secondsFromMs(ms) {
  const n = Number(ms)
  if (!Number.isFinite(n)) return '—'
  return `${(n / 1000).toFixed(1)}s`
}

// Status is never encoded by colour alone — always glyph + word.
const STATUS = {
  queued: { glyph: '○', label: 'queued' },
  running: { glyph: '⟳', label: 'running' },
  done: { glyph: '✓', label: 'done' },
  failed: { glyph: '✕', label: 'failed' },
}

function StatusTag({ status }) {
  const s = STATUS[status] || STATUS.queued
  return (
    <span className={`status-tag status-tag--${status}`}>
      <span className="status-tag__glyph" aria-hidden="true">{s.glyph}</span>
      {s.label}
    </span>
  )
}

// One expert row: role + name, status, verdict, score bar, fix, expandable notes.
// The identity block is a button so the expert's editable profile opens on click.
function ExpertRow({ expert, onOpen }) {
  const { role, name, status, note, elapsed_ms: elapsedMs, error } = expert
  const verdict = note?.verdict
  const score = pct(note?.score)
  const hasNotes = (note?.strengths?.length || 0) + (note?.issues?.length || 0) > 0

  return (
    <li className="expert">
      <div className="expert__top">
        <button type="button" className="expert__open" onClick={onOpen}>
          <p className="expert__role">{role}</p>
          <p className="expert__name">
            {name}
            <span className="expert__hint"> · edit profile</span>
          </p>
        </button>
        <div className="expert__flags">
          {verdict && status === 'done' && (
            <span className={`verdict verdict--${verdict}`}>{verdict}</span>
          )}
          <StatusTag status={status} />
        </div>
      </div>

      {status === 'done' && note && (
        <>
          <div className="score" title={`Score ${formatNumber(note.score)} of 100`}>
            <div
              className="score__bar"
              role="progressbar"
              aria-label={`${role} score`}
              aria-valuenow={Math.round(score)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="score__fill" style={{ width: `${score}%` }} />
            </div>
            <span className="score__num">{formatNumber(note.score)}<span className="score__max">/100</span></span>
          </div>

          {note.fix_suggestion && (
            <p className="expert__fix">
              <span className="expert__fix-label">Fix</span>
              {note.fix_suggestion}
            </p>
          )}

          {hasNotes && (
            <details className="disclose">
              <summary className="disclose__summary">Strengths and issues</summary>
              <div className="disclose__body">
                {note.strengths?.length > 0 && (
                  <div className="notelist">
                    <p className="notelist__label">Strengths</p>
                    <ul className="notelist__items">
                      {note.strengths.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
                {note.issues?.length > 0 && (
                  <div className="notelist">
                    <p className="notelist__label">Issues</p>
                    <ul className="notelist__items notelist__items--issue">
                      {note.issues.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            </details>
          )}
          {elapsedMs != null && (
            <p className="expert__elapsed">finished in {secondsFromMs(elapsedMs)}</p>
          )}
        </>
      )}

      {status === 'failed' && (
        <p className="expert__error">This lens didn’t return a note: {error || 'unknown error'}</p>
      )}

      {status === 'queued' && (
        <p className="expert__waiting">Waiting for the pro model to deliberate…</p>
      )}
    </li>
  )
}

function audienceLineText(entry) {
  if (entry.error) {
    return `✕ [${entry.id}] error · ${entry.error}`
  }
  const r = entry.reaction || {}
  const move = r.will_continue ? 'continues' : 'drops'
  const reason = (r.reason || '').replace(/\s+/g, ' ').trim()
  return `✓ [${entry.segment || 'listener'}] hook ${formatNumber(r.hook_score)} · ${move} · "${reason}"`
}

// Flatten the fetched personas into one editable roster, pinning each agent's
// kind by the bucket it arrived in so re-bucketing on edit is always reliable.
function buildRoster(data) {
  return [
    ...(data?.experts || []).map((a) => cloneAgent({ ...a, kind: 'expert' })),
    ...(data?.audience || []).map((a) => cloneAgent({ ...a, kind: 'audience' })),
  ]
}

// A clickable roster chip: name + role/segment + a compact attribute summary.
function RosterCard({ agent, onOpen }) {
  const isAudience = agent.kind === 'audience'
  const subtitle = isAudience ? agent.segment : agent.role
  const summary = isAudience ? audienceSummary(agent) : expertSummary(agent)
  return (
    <button type="button" className="cast-card" onClick={onOpen}>
      <span className="cast-card__name">{agent.name}</span>
      {subtitle && <span className="cast-card__role">{subtitle}</span>}
      {summary && <span className="cast-card__sum">{summary}</span>}
    </button>
  )
}

// One labelled roster group ('Expert panel' or 'Audience') of clickable chips.
// The group is derived from the combined roster by the agent's current kind, so
// flipping an agent's Type in its profile moves its chip here instantly.
function RosterGroup({ title, agents, emptyLabel, onOpen }) {
  return (
    <section className="roster-group" aria-label={title}>
      <div className="roster-group__head">
        <h3 className="roster-group__title">{title}</h3>
        <span className="roster-group__count">{agents.length}</span>
      </div>
      {agents.length === 0 ? (
        <p className="panel__placeholder">{emptyLabel}</p>
      ) : (
        <div className="cast">
          {agents.map((agent) => (
            <RosterCard
              agent={agent}
              key={agent.id}
              onOpen={() => onOpen(agent.id)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

export default function WritersRoom() {
  const toast = useToast()
  const [title, setTitle] = useState('Andhera')
  const [episode, setEpisode] = useState('7')
  const [text, setText] = useState(SAMPLE_SCRIPT)

  const [streaming, setStreaming] = useState(false)
  const [hasRun, setHasRun] = useState(false)
  const [error, setError] = useState(null)

  const [runMeta, setRunMeta] = useState(null) // { audience_count, story }
  const [experts, setExperts] = useState([])
  const [audienceLog, setAudienceLog] = useState([])
  const [orchestrator, setOrchestrator] = useState(null)
  const [result, setResult] = useState(null)

  // One combined, editable roster is the single source of truth. Each entry
  // carries its own `kind` ('expert' | 'audience'); the Expert panel and the
  // Audience group are just views derived from that field, so flipping an
  // agent's Type in its profile re-buckets it everywhere at once — both the
  // on-screen chips and the run payload.
  const [roster, setRoster] = useState([])
  const [rosterError, setRosterError] = useState(null)
  const [activeAgentId, setActiveAgentId] = useState(null) // agent id | null

  const abortRef = useRef(null)
  const abortedRef = useRef(false)
  const logRef = useRef(null)

  // Load the base rosters once on mount; store editable copies in one array.
  // The source array pins each agent's kind so re-bucketing is always reliable.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await getPersonas()
        if (cancelled) return
        setRoster(buildRoster(data))
        setRosterError(null)
      } catch (err) {
        if (!cancelled) setRosterError(err?.message || 'Could not load the agents.')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function resetRosters() {
    try {
      const data = await getPersonas()
      setRoster(buildRoster(data))
      setRosterError(null)
      toast.success('Agents reset to defaults.')
    } catch (err) {
      setRosterError(err?.message || 'Could not reload the agents.')
    }
  }

  // Announce the room's outcomes wherever the user is in the studio.
  useStatusToast(error, (e) => toast.error(`The Writers Room run couldn't finish. ${e}`))
  useStatusToast(rosterError, (e) => toast.error(`Writers Room agents: ${e}`))
  useStatusToast(result, (r) =>
    toast.success(`The Writers Room finished in ${secondsFromMs(r.elapsed_ms)}.`),
  )

  // Views derived from the current kind of each agent.
  const expertGroup = useMemo(() => roster.filter((a) => a.kind === 'expert'), [roster])
  const audienceGroup = useMemo(() => roster.filter((a) => a.kind === 'audience'), [roster])

  const segmentOpts = useMemo(() => segmentOptions(audienceGroup), [audienceGroup])

  // Resolve a clicked agent (roster chip, expert row, or fanned-out audience
  // log line) back to its roster entry, then open its profile. Audience log ids
  // look like "<base-id>-<n>", so a prefix match reunites a clone with its base.
  // Matching is kind-agnostic: we search the whole roster by id, then segment,
  // then name.
  function openAgent({ id, name, segment } = {}) {
    let found = null
    if (id) {
      found = roster.find((a) => a.id === id) || roster.find((a) => id.startsWith(`${a.id}-`))
    }
    if (!found && segment) found = roster.find((a) => a.segment === segment)
    if (!found && name) found = roster.find((a) => a.name === name)
    if (found) setActiveAgentId(found.id)
  }

  // Apply an edit from the profile drawer back into the combined roster by id.
  // A changed kind simply lands on the entry and the derived groups recompute.
  function updateAgent(updated) {
    setRoster((prev) => prev.map((a) => (a.id === updated.id ? updated : a)))
  }

  const activeAgentObj = useMemo(
    () => (activeAgentId ? roster.find((a) => a.id === activeAgentId) || null : null),
    [activeAgentId, roster],
  )

  // Auto-scroll the console to the newest line as the audience reacts.
  useEffect(() => {
    const el = logRef.current
    if (!el) return
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    el.scrollTo({ top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth' })
  }, [audienceLog.length])

  function handleEvent(ev) {
    switch (ev?.type) {
      case 'run_started':
        setRunMeta({ audience_count: ev.audience_count || 0, story: ev.story })
        setExperts(
          (ev.experts || []).map((e) => ({
            id: e.id,
            name: e.name,
            role: e.role || 'Expert',
            status: 'queued',
            note: null,
            elapsed_ms: null,
            error: null,
          })),
        )
        break
      case 'expert_done':
        setExperts((prev) =>
          prev.map((e) =>
            e.id === ev.id
              ? { ...e, status: 'done', note: ev.note, elapsed_ms: ev.elapsed_ms, name: ev.name ?? e.name, role: ev.role ?? e.role }
              : e,
          ),
        )
        break
      case 'expert_error':
        setExperts((prev) =>
          prev.map((e) =>
            e.id === ev.id ? { ...e, status: 'failed', error: ev.error } : e,
          ),
        )
        break
      case 'audience_done':
        setAudienceLog((prev) => [
          ...prev,
          { id: ev.id, name: ev.name, segment: ev.segment, reaction: ev.reaction, error: null },
        ])
        break
      case 'audience_error':
        setAudienceLog((prev) => [...prev, { id: ev.id, error: ev.error, reaction: null }])
        break
      case 'orchestrator':
        setOrchestrator(ev)
        break
      case 'done':
        setResult(ev)
        break
      case 'error':
        // Terminal error line emitted by the backend mid-stream.
        setError(ev.error || 'The run failed on the server.')
        break
      default:
        break
    }
  }

  async function run() {
    if (streaming) return
    abortedRef.current = false
    const controller = new AbortController()
    abortRef.current = controller

    setStreaming(true)
    setHasRun(true)
    setError(null)
    setRunMeta(null)
    setExperts([])
    setAudienceLog([])
    setOrchestrator(null)
    setResult(null)

    try {
      await writersRoomStream(
        { story: { title, episode, text }, experts: expertGroup, audience: audienceGroup },
        handleEvent,
        controller.signal,
      )
    } catch (err) {
      if (!abortedRef.current && err?.name !== 'AbortError') {
        setError(err?.message || 'The stream failed. Check the backend and try again.')
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  function stop() {
    abortedRef.current = true
    abortRef.current?.abort()
  }

  // ---- Derived live figures ------------------------------------------------
  const expertCount = experts.length
  const audienceTotal = runMeta?.audience_count ?? 0
  const totalAgents = expertCount + audienceTotal
  const expertsDone = experts.filter((e) => e.status !== 'queued').length
  const audienceDone = audienceLog.length
  const doneCount = expertsDone + audienceDone

  const audienceStats = useMemo(() => {
    const responded = audienceLog.filter((a) => !a.error && a.reaction)
    const following = responded.filter((a) => a.reaction.will_continue).length
    const hookSum = responded.reduce((sum, a) => sum + (Number(a.reaction.hook_score) || 0), 0)
    return {
      responded: responded.length,
      followingPct: responded.length ? (following / responded.length) * 100 : 0,
      avgHook: responded.length ? hookSum / responded.length : 0,
    }
  }, [audienceLog])

  const phase = (() => {
    if (result) return `Done in ${secondsFromMs(result.elapsed_ms)}`
    if (orchestrator) return 'Fusing verdicts…'
    if (!runMeta) return streaming ? 'Starting run…' : ''
    if (doneCount === 0) return `Dispatching ${expertCount} experts + ${audienceTotal} listeners…`
    return `${doneCount}/${totalAgents} agents done`
  })()

  const progress = result ? 100 : totalAgents ? (doneCount / totalAgents) * 100 : streaming ? 8 : 0
  const consensus = orchestrator?.consensus || result?.result?.consensus
  const finalAudience = orchestrator?.audience || result?.result?.audience
  const summary = orchestrator?.expert_summary

  const canRun = text.trim().length > 0 && !streaming
  const showConsole = hasRun || streaming
  const showEmpty = !showConsole && !error

  return (
    <div className="wr">
      <div className="wr-body">
        {/* ---- Story input ---- */}
        <section className="composer" aria-labelledby="composer-heading">
          <h2 id="composer-heading" className="visually-hidden">Episode to run</h2>
          <div className="composer__row">
            <label className="field">
              <span className="field__label">Title</span>
              <input
                className="field__input"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={streaming}
                placeholder="Story title"
              />
            </label>
            <label className="field field--sm">
              <span className="field__label">Episode</span>
              <input
                className="field__input"
                value={episode}
                onChange={(e) => setEpisode(e.target.value)}
                disabled={streaming}
                placeholder="e.g. 7"
              />
            </label>
          </div>

          <label className="field">
            <span className="field__label">Script excerpt</span>
            <textarea
              className="field__area"
              value={text}
              onChange={(e) => setText(e.target.value)}
              disabled={streaming}
              rows={11}
              spellCheck={false}
              placeholder="Paste an episode script here…"
            />
          </label>

          <div className="composer__actions">
            {streaming ? (
              <button type="button" className="btn btn--ghost" onClick={stop}>
                Stop
              </button>
            ) : (
              <button type="button" className="btn btn--primary" onClick={run} disabled={!canRun}>
                Run the Writers Room
              </button>
            )}
            <span className="composer__note">
              {streaming
                ? 'Listeners answer first; the expert panel follows.'
                : 'Your expert panel and a simulated audience weigh in at once — edit any agent below.'}
            </span>
          </div>
        </section>

        {/* ---- Orchestrator strip ---- */}
        {showConsole && (
          <section className="strip" role="status" aria-live="polite" aria-label="Run progress">
            <div className="strip__line">
              <span className={`strip__dot${streaming ? ' strip__dot--live' : ''}`} aria-hidden="true" />
              <span className="strip__phase">{phase || 'Ready'}</span>
              {totalAgents > 0 && (
                <span className="strip__count">{doneCount}/{totalAgents} agents</span>
              )}
            </div>
            <div
              className="strip__track"
              role="progressbar"
              aria-label="Agents finished"
              aria-valuenow={Math.round(progress)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div className="strip__fill" style={{ width: `${progress}%` }} />
            </div>
          </section>
        )}

        {/* ---- Error ---- */}
        {error && (
          <section className="alert" role="alert">
            <p className="alert__title">
              <span aria-hidden="true">✕ </span>The run couldn’t finish
            </p>
            <p className="alert__msg">{error}</p>
            <p className="alert__hint">
              Check that the backend is reachable, then run the room again.
            </p>
          </section>
        )}

        {/* ---- Consensus: the single highlighted insight ---- */}
        {consensus && (
          <section className="insight" aria-label="Consensus">
            <p className="insight__label">Consensus</p>
            <p className="insight__text">{consensus}</p>
            {summary && (
              <p className="insight__meta">
                {summary.count} experts · avg {formatNumber(summary.avg_score, 1)}/100 ·{' '}
                {summary.verdicts.strong} strong · {summary.verdicts.mixed} mixed ·{' '}
                {summary.verdicts.weak} weak
              </p>
            )}
          </section>
        )}

        {/* ---- Empty state: the editable cast ---- */}
        {showEmpty && (
          <section className="empty" aria-label="The room">
            <p className="empty__lead">
              Run an episode and the room convenes at once. Listeners react on the
              fast model, the expert panel deliberates on the pro model, and an
              orchestrator fuses both into one verdict — streamed here as each voice
              lands.
            </p>

            <div className="roster">
              <div className="roster__bar">
                <p className="roster__hint">
                  Tap any agent to edit their profile. Changes apply to the next run.
                </p>
                <button type="button" className="btn btn--ghost" onClick={resetRosters}>
                  Reset to defaults
                </button>
              </div>

              {rosterError && (
                <p className="roster__error" role="alert">
                  <span aria-hidden="true">✕ </span>{rosterError}
                </p>
              )}

              <div className="roster__groups">
                <RosterGroup
                  title="Expert panel"
                  agents={expertGroup}
                  emptyLabel={
                    roster.length === 0
                      ? 'Loading agents…'
                      : "No experts yet — set an agent's Type to expert."
                  }
                  onOpen={(id) => openAgent({ id })}
                />
                <RosterGroup
                  title="Audience"
                  agents={audienceGroup}
                  emptyLabel={
                    roster.length === 0
                      ? 'Loading agents…'
                      : "No listeners yet — set an agent's Type to audience."
                  }
                  onOpen={(id) => openAgent({ id })}
                />
              </div>
            </div>
          </section>
        )}

        {/* ---- Live console: expert panel + audience stream ---- */}
        {showConsole && (
          <div className="console">
            <section className="panel" aria-labelledby="experts-heading">
              <div className="panel__head">
                <h2 id="experts-heading" className="panel__title">Expert panel</h2>
                <span className="panel__meta">
                  {expertsDone}/{expertCount || '—'} done
                </span>
              </div>
              {experts.length === 0 ? (
                <p className="panel__placeholder">Assembling the panel…</p>
              ) : (
                <ul className="experts">
                  {experts.map((e) => (
                    <ExpertRow
                      expert={e}
                      key={e.id}
                      onOpen={() => openAgent({ id: e.id, name: e.name })}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section className="panel" aria-labelledby="audience-heading">
              <div className="panel__head">
                <h2 id="audience-heading" className="panel__title">Audience stream</h2>
                <span className="panel__meta">
                  {audienceDone}/{audienceTotal || '—'} listeners
                </span>
              </div>

              <div className="tallies">
                <div className="tally">
                  <span className="tally__label">Still following</span>
                  <span className="tally__value">
                    {audienceStats.responded ? `${formatNumber(audienceStats.followingPct)}%` : '—'}
                  </span>
                </div>
                <div className="tally">
                  <span className="tally__label">Avg. hook</span>
                  <span className="tally__value">
                    {audienceStats.responded ? formatNumber(audienceStats.avgHook, 1) : '—'}
                  </span>
                </div>
              </div>

              <div className="log" ref={logRef} role="log" aria-live="polite" aria-label="Listener reactions">
                {audienceLog.length === 0 ? (
                  <p className="log__idle">Waiting for the first listener…</p>
                ) : (
                  audienceLog.map((entry, i) => (
                    <button
                      type="button"
                      className={`log__line${entry.error ? ' log__line--err' : ''}`}
                      key={`${entry.id}-${i}`}
                      onClick={() =>
                        openAgent({
                          id: entry.id,
                          segment: entry.segment,
                          name: entry.name,
                        })
                      }
                    >
                      {audienceLineText(entry)}
                    </button>
                  ))
                )}
              </div>
            </section>
          </div>
        )}

        {/* ---- Orchestrator result: audience verdict ---- */}
        {finalAudience && (
          <section className="verdict-block" aria-labelledby="verdict-heading">
            <h2 id="verdict-heading" className="panel__title">Audience verdict</h2>
            <div className="verdict-meters">
              <div className="meter">
                <div className="meter__head">
                  <span className="meter__label">Still following</span>
                  <span className="meter__value">{formatNumber(finalAudience.following_pct)}%</span>
                </div>
                <div className="meter__track">
                  <div className="meter__fill" style={{ width: `${pct(finalAudience.following_pct)}%` }} />
                </div>
              </div>
              <div className="meter">
                <div className="meter__head">
                  <span className="meter__label">Avg. engagement</span>
                  <span className="meter__value">{formatNumber(finalAudience.avg_engagement, 1)}</span>
                </div>
                <div className="meter__track">
                  <div className="meter__fill" style={{ width: `${engagementWidth(finalAudience.avg_engagement)}%` }} />
                </div>
              </div>
            </div>

            {finalAudience.comprehension && (
              <p className="verdict-comprehension">{finalAudience.comprehension}</p>
            )}

            {finalAudience.confusion_points?.length > 0 && (
              <div className="verdict-sub">
                <p className="verdict-sub__label">Where they got lost</p>
                <div className="chips">
                  {finalAudience.confusion_points.map((c, i) => (
                    <span className="chip" key={i}>{c}</span>
                  ))}
                </div>
              </div>
            )}

            {finalAudience.representative_quotes?.length > 0 && (
              <div className="verdict-sub">
                <p className="verdict-sub__label">In their words</p>
                <ul className="quotes">
                  {finalAudience.representative_quotes.map((q, i) => (
                    <li className="quote" key={i}>“{q}”</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </div>

      {/* ---- Agent profile drawer (edits reflect in real time) ---- */}
      {activeAgentObj && (
        <AgentProfile
          agent={activeAgentObj}
          segmentOptions={segmentOpts}
          onChange={updateAgent}
          onClose={() => setActiveAgentId(null)}
        />
      )}
    </div>
  )
}
