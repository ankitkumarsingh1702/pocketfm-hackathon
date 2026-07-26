import { signed } from '../../utils/format'
import { Button, Icon, MetricNumber, Pill, ProgressLine, ScoreGauge, SurfaceCard } from '../primitives'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/** Visually-hidden text for screen-reader-only announcements. */
const srOnly = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0 0 0 0)',
  whiteSpace: 'nowrap',
  border: 0,
}

function EndingCard({ label, text, score, gaugeLabel, elevated, audio }) {
  return (
    <SurfaceCard elevated={elevated}>
      <div
        className="label-upper"
        style={{
          marginBottom: 20,
          fontSize: 11,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <span>{label}</span>
        {audio?.styleLabel && <Pill label={audio.styleLabel} />}
      </div>
      <p style={{ margin: '0 0 24px', fontSize: 15, lineHeight: 1.6, color: 'var(--ink)' }}>
        &ldquo;{text}&rdquo;
      </p>
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <ScoreGauge score={score} label={gaugeLabel} />
      </div>
      {audio?.url && (
        <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <Button variant="secondary" onClick={audio.onToggle}>
            <Icon name={audio.isPlaying ? 'pause' : 'play'} size={16} />
            {audio.isPlaying ? 'Stop' : audio.playLabel}
          </Button>
          {audio.isPlaying && <ProgressLine label="Now playing" value={audio.progress} />}
        </div>
      )}
    </SurfaceCard>
  )
}

/**
 * Cliffhanger Optimizer results. Pure view of the cliffhanger view-model:
 * before → after hook scores, the original vs optimized endings, and the
 * rationale behind the rewrite. The "hear the difference" bar and per-card
 * players turn the score lift into an audible A/B (state comes from `narration`).
 */
export default function CliffhangerOptimizerTab({ loading, error, data, narration }) {
  if (loading) return <LoadingState label="Scoring rewrites against the listener panel…" />
  if (error) return <ErrorState message={error} />
  if (!data) {
    return (
      <EmptyState
        title="No rewrite yet"
        hint="Run the optimizer to rewrite the episode's ending and A/B test the hook lift."
      />
    )
  }

  const n = narration ?? {}
  const clips = n.clips
  const isLoading = n.status === 'loading'
  const isError = n.status === 'error'

  const onHero = () => {
    if (isLoading) return
    if (n.status === 'idle' || isError) {
      n.generate?.(data.original, data.rewrite, { autoplay: true })
    } else if (n.playing) {
      n.stop?.()
    } else {
      n.playSequence?.()
    }
  }

  const heroLabel = isLoading
    ? 'Voicing…'
    : isError
      ? 'Retry'
      : n.playing
        ? 'Stop'
        : 'Hear the difference'

  const caption =
    n.playing === 'original'
      ? 'Now playing · Original'
      : n.playing === 'optimized'
        ? 'Now playing · Optimized'
        : isLoading
          ? 'Synthesizing narration…'
          : n.status === 'ready'
            ? 'Original, then the optimized cut'
            : 'Same scene, opposite delivery'

  const cardAudio = (key, playLabel, styleLabel) =>
    clips
      ? {
          url: clips[key]?.url,
          styleLabel,
          playLabel,
          isPlaying: n.playing === key,
          progress: n.progress,
          onToggle: () => (n.playing === key ? n.stop?.() : n.playOne?.(key)),
        }
      : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40, paddingTop: 8 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 20, flexWrap: 'wrap' }}>
        <MetricNumber value={data.before} size="lg" tone="muted" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 40, color: 'var(--accent)' }}>
          &rarr;
        </span>
        <MetricNumber value={data.after} size="lg" tone="accent" />
        <span
          className="label-upper"
          style={{ fontSize: 12, fontWeight: 600, alignSelf: 'center' }}
        >
          Hook Score, Before &rarr; After
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 700,
            fontSize: 18,
            color: data.improved ? 'var(--accent)' : 'var(--muted)',
            alignSelf: 'center',
          }}
        >
          {signed(data.lift)}
        </span>
      </div>

      {/* Hear the difference — the score lift, made audible. */}
      {narration && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 16 }}>
            <Button variant="primary" onClick={onHero} disabled={isLoading}>
              <Icon name={n.playing ? 'stop' : 'volume'} size={18} />
              {heroLabel}
            </Button>
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>{caption}</span>
          </div>
          {isError && (
            <span style={{ fontSize: 13, color: 'var(--muted)' }}>
              {n.error || 'Couldn’t voice that.'} Press retry.
            </span>
          )}
          <span aria-live="polite" style={srOnly}>
            {n.playing ? `Playing ${n.playing} ending` : ''}
          </span>
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 24,
          alignItems: 'start',
        }}
      >
        <EndingCard
          label="Original Ending"
          text={data.original}
          score={data.before}
          gaugeLabel="ORIGINAL"
          audio={cardAudio('original', 'Play original', 'Flat · passive')}
        />
        <EndingCard
          label="Optimized Ending"
          text={data.rewrite}
          score={data.after}
          gaugeLabel="OPTIMIZED"
          elevated
          audio={cardAudio('optimized', 'Play optimized', 'Dramatic · in-character')}
        />
      </div>

      {data.rationale && (
        <div style={{ maxWidth: 720 }}>
          <div className="label-upper" style={{ fontSize: 11, marginBottom: 8 }}>
            Why It Works
          </div>
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: 'var(--ink)' }}>
            {data.rationale}
          </p>
        </div>
      )}
    </div>
  )
}
