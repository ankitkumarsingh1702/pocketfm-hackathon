import { STAGE_LABELS, STAGE_ORDER, STAGE_SHORT } from '../../config/genre'
import { ProgressLine } from '../primitives'
import ActivityLog from './ActivityLog'

/** mm:ss for the elapsed clock. */
function clock(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/** One entry in the extract → rewrite → verify checklist. */
function StageMarker({ name, state }) {
  const colors = {
    done: { mark: '✓', color: 'var(--muted)', weight: 500 },
    current: { mark: '▸', color: 'var(--accent-text-sm)', weight: 600 },
    pending: { mark: '·', color: 'var(--dim)', weight: 400 },
  }[state]

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 13,
        color: colors.color,
        fontWeight: colors.weight,
      }}
    >
      <span aria-hidden="true">{colors.mark}</span>
      {STAGE_SHORT[name]}
      {state === 'current' && <span className="sr-only"> (in progress)</span>}
    </span>
  )
}

/**
 * Live state of a running job.
 *
 * A conversion is five to eight minutes, which is long enough that silence
 * reads as failure. Five independent signals say it is still alive: which stage
 * the pipeline is in, the service's own note ("scene 4 of 7"), a determinate bar
 * driven by the job's `percent`, a running clock, and the full activity log of
 * everything done so far.
 *
 * Only the current-step line is a live region. The log below it grows on every
 * poll, and announcing the whole thing each time would bury the one line that
 * changed.
 */
export default function RunStatus({ job, elapsed, onStop }) {
  const queued = !job || job.status === 'queued'
  const stage = job?.stage
  const label = stage ? STAGE_LABELS[stage] || stage : 'Queued'
  const percent = typeof job?.percent === 'number' ? job.percent : undefined

  const currentIndex = stage ? STAGE_ORDER.indexOf(stage) : -1

  return (
    <section
      style={{
        marginTop: 32,
        padding: 'var(--space-6)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        maxWidth: 720,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
        <div aria-live="polite">
          <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>
            {queued ? 'Waiting for a worker' : label}
          </div>
          {job?.progress && (
            <div style={{ fontSize: 14, color: 'var(--muted)', marginTop: 4 }}>
              {job.progress}
              {job.steps > 0 && (
                <span className="font-mono-num" style={{ color: 'var(--dim)' }}>
                  {' '}
                  · step {job.step ?? 0} of {job.steps}
                </span>
              )}
            </div>
          )}
        </div>
        <div
          className="font-mono-num"
          style={{ fontSize: 15, color: 'var(--muted)', whiteSpace: 'nowrap' }}
        >
          {percent != null && (
            <span style={{ color: 'var(--ink)', fontWeight: 600 }}>{percent}% · </span>
          )}
          {clock(elapsed)}
        </div>
      </div>

      <ProgressLine label={queued ? 'Queued' : label} value={percent} />

      {/* Where this sits in the pipeline overall, not just within one stage. */}
      {!queued && currentIndex >= 0 && (
        <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
          {STAGE_ORDER.map((name, index) => (
            <StageMarker
              key={name}
              name={name}
              state={
                index < currentIndex ? 'done' : index === currentIndex ? 'current' : 'pending'
              }
            />
          ))}
        </div>
      )}

      <ActivityLog events={job?.events} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, flex: '1 1 260px' }}>
          A conversion takes five to eight minutes — one model call per scene, then
          three alignment votes.
        </p>
        <button
          type="button"
          onClick={onStop}
          style={{
            minHeight: 44,
            padding: '0 18px',
            background: 'var(--canvas)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--ink)',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Stop watching
        </button>
      </div>

      {job?.id && (
        <div style={{ fontSize: 12, color: 'var(--dim)', fontFamily: 'var(--font-mono)' }}>
          job {job.id}
        </div>
      )}
    </section>
  )
}
