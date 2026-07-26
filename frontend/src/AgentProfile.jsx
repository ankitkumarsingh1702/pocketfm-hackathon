import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import {
  GENDERS,
  CITIES,
  GENRES,
  MAX_GENRES,
  DEFAULT_SEGMENTS,
  effectiveTemp,
  hasGenre,
  toggleGenre,
} from './lib/agents'

// A right-side drawer for editing one agent (expert or audience listener).
// Every control edits in place: each change calls onChange(updatedAgent) so the
// parent roster — and therefore the next run — reflects the edit in real time.
//
// Name is a free-text input, and Type (kind) is a dropdown that live re-buckets
// the agent between the Expert panel and the Audience group. Which fields show
// follows the current kind: experts get a free-text Role; audience listeners get
// segment / gender / city / age / genres.
//
// Props:
//   agent          the roster persona to edit (source of truth lives in parent)
//   segmentOptions distinct segment labels for the audience segment <select>
//   onChange       (updatedAgent) => void, called on every edit
//   onClose        () => void, called by Done / scrim / Escape
export default function AgentProfile({ agent, segmentOptions, onChange, onClose }) {
  const closeRef = useRef(null)

  // Move focus to Done on open, and let Escape dismiss the drawer.
  useEffect(() => {
    closeRef.current?.focus()
    function onKey(event) {
      if (event.key === 'Escape') onClose?.()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  if (!agent) return null

  const isAudience = agent.kind === 'audience'
  const segments = segmentOptions?.length ? segmentOptions : DEFAULT_SEGMENTS
  const temp = effectiveTemp(agent)
  const base = `agent-profile-${agent.id}`
  const nameId = `${base}-name`
  const kindId = `${base}-kind`
  const roleId = `${base}-role`
  const ageId = `${base}-age`
  const tempId = `${base}-temp`

  const genreCount = (agent.genres || []).length
  const atGenreCap = genreCount >= MAX_GENRES

  const patch = (changes) => onChange?.({ ...agent, ...changes })

  // Age is free-typed: no clamping and no segment-driven band. Blank clears it.
  const changeAge = (raw) => {
    if (raw === '') return patch({ age: null })
    const n = Number(raw)
    if (!Number.isFinite(n)) return
    patch({ age: Math.round(n) })
  }

  // Rendered into <body> so no transformed/animated ancestor can capture the
  // fixed positioning — the sheet always covers the whole viewport and slides
  // in from the screen's right edge, not the panel's.
  return createPortal(
    <div className="drawer" role="presentation">
      <div className="drawer__scrim" onClick={onClose} aria-hidden="true" />
      <aside
        className="drawer__panel"
        role="dialog"
        aria-modal="true"
        aria-label={`Edit ${agent.name || 'agent'} profile`}
      >
        <header className="drawer__head">
          <div className="drawer__id">
            <p className="drawer__kind">{isAudience ? 'Audience listener' : 'Expert lens'}</p>
            <label className="drawer__namefield" htmlFor={nameId}>
              <span className="ctl__label">Name</span>
              <input
                id={nameId}
                className="drawer__name-input"
                type="text"
                value={agent.name || ''}
                onChange={(event) => patch({ name: event.target.value })}
                placeholder="Name this agent"
              />
            </label>
          </div>
          <button
            type="button"
            className="btn btn--primary drawer__close"
            onClick={onClose}
            ref={closeRef}
          >
            Done
          </button>
        </header>

        <div className="drawer__body">
          <label className="ctl" htmlFor={kindId}>
            <span className="ctl__label">Type</span>
            <select
              id={kindId}
              className="ctl__select"
              value={agent.kind || 'audience'}
              onChange={(event) => patch({ kind: event.target.value })}
            >
              <option value="audience">audience</option>
              <option value="expert">expert</option>
            </select>
            <span className="ctl__hint">
              Moves this agent between the audience and the expert panel.
            </span>
          </label>

          {!isAudience && (
            <label className="ctl" htmlFor={roleId}>
              <span className="ctl__label">Role</span>
              <input
                id={roleId}
                className="ctl__text"
                type="text"
                value={agent.role || ''}
                onChange={(event) => patch({ role: event.target.value })}
                placeholder="e.g. Story Editor"
              />
            </label>
          )}

          {isAudience && (
            <>
              <div className="form-grid">
                <label className="ctl">
                  <span className="ctl__label">Segment</span>
                  <select
                    className="ctl__select"
                    value={agent.segment || ''}
                    onChange={(event) => patch({ segment: event.target.value })}
                  >
                    {agent.segment && !segments.includes(agent.segment) && (
                      <option value={agent.segment}>{agent.segment}</option>
                    )}
                    {segments.map((segment) => (
                      <option key={segment} value={segment}>{segment}</option>
                    ))}
                  </select>
                </label>

                <label className="ctl">
                  <span className="ctl__label">Gender</span>
                  <select
                    className="ctl__select"
                    value={agent.gender || ''}
                    onChange={(event) => patch({ gender: event.target.value })}
                  >
                    <option value="">Unspecified</option>
                    {GENDERS.map((gender) => (
                      <option key={gender} value={gender}>{gender}</option>
                    ))}
                  </select>
                </label>

                <label className="ctl">
                  <span className="ctl__label">City</span>
                  <select
                    className="ctl__select"
                    value={agent.city || ''}
                    onChange={(event) => patch({ city: event.target.value })}
                  >
                    <option value="">Unspecified</option>
                    {agent.city && !CITIES.includes(agent.city) && (
                      <option value={agent.city}>{agent.city}</option>
                    )}
                    {CITIES.map((city) => (
                      <option key={city} value={city}>{city}</option>
                    ))}
                  </select>
                </label>

                <label className="ctl" htmlFor={ageId}>
                  <span className="ctl__label">Age</span>
                  <input
                    id={ageId}
                    className="ctl__num"
                    type="number"
                    min={1}
                    max={120}
                    value={agent.age ?? ''}
                    onChange={(event) => changeAge(event.target.value)}
                    placeholder="—"
                  />
                  <span className="ctl__hint">Any age; leave blank to skip.</span>
                </label>
              </div>

              <fieldset className="ctl ctl--genres">
                <legend className="ctl__label">Genres</legend>
                <div className="checks">
                  {GENRES.map((genre) => {
                    const checked = hasGenre(agent.genres, genre)
                    const locked = !checked && atGenreCap
                    return (
                      <label className={`check${locked ? ' check--locked' : ''}`} key={genre}>
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={locked}
                          onChange={() => patch({ genres: toggleGenre(agent.genres, genre) })}
                        />
                        <span>{genre}</span>
                      </label>
                    )
                  })}
                </div>
                <span className="ctl__hint">
                  Up to {MAX_GENRES} genres{atGenreCap ? ' · limit reached' : ''}
                </span>
              </fieldset>
            </>
          )}

          <div className="ctl">
            <div className="ctl__row">
              <span className="ctl__label" id={tempId}>Temperature</span>
              <span className="ctl__value">{temp.toFixed(1)}</span>
            </div>
            <input
              className="ctl__range"
              type="range"
              min={0}
              max={1.5}
              step={0.1}
              value={temp}
              onChange={(event) => patch({ temperature: Number(event.target.value) })}
              aria-labelledby={tempId}
            />
            <span className="ctl__hint">Lower is steadier; higher is more inventive.</span>
          </div>

          <label className="ctl">
            <span className="ctl__label">System prompt</span>
            <textarea
              className="ctl__area"
              value={agent.system_prompt || ''}
              onChange={(event) => patch({ system_prompt: event.target.value })}
              rows={9}
              spellCheck={false}
            />
          </label>
        </div>
      </aside>
    </div>,
    document.body,
  )
}
