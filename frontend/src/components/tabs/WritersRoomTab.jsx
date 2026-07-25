import ExpertNote from '../ExpertNote'
import { EmptyState, ErrorState, LoadingState } from '../StateViews'

/**
 * Writers Room results. Pure view of the writers-room view-model: a grid of
 * expert notes plus the panel consensus.
 */
export default function WritersRoomTab({ loading, error, data }) {
  if (loading) return <LoadingState label="Convening the expert panel…" />
  if (error) return <ErrorState message={error} />
  if (!data) {
    return (
      <EmptyState
        title="No panel notes yet"
        hint="Run the Writers Room to gather craft feedback from six expert agents."
      />
    )
  }

  const cols = 3
  return (
    <div style={{ paddingTop: 8 }}>
      <p style={{ margin: '32px 0 0', fontSize: 14, color: 'var(--muted)', maxWidth: 640 }}>
        AI Writers Room: expert agents — director, editor, critic, psychologist, historian, and
        audience proxy — weigh in simultaneously.
      </p>

      <div
        style={{
          marginTop: 20,
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          overflow: 'hidden',
          background: 'var(--surface-raised)',
        }}
      >
        {data.notes.map((note, i) => {
          const row = Math.floor(i / cols)
          const totalRows = Math.ceil(data.notes.length / cols)
          return (
            <div
              key={i}
              style={{
                borderRight: i % cols !== cols - 1 ? '1px solid var(--border)' : 'none',
                borderBottom: row < totalRows - 1 ? '1px solid var(--border)' : 'none',
              }}
            >
              <ExpertNote note={note} />
            </div>
          )
        })}
      </div>

      {data.consensus && (
        <div
          style={{
            marginTop: 24,
            padding: 'var(--space-6)',
            border: '1.5px solid var(--accent)',
            borderRadius: 'var(--radius-md)',
            background: 'var(--surface-raised)',
            boxShadow: 'var(--shadow-sm)',
          }}
        >
          <div className="label-upper" style={{ fontSize: 11, marginBottom: 8 }}>
            Panel Consensus
          </div>
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: 'var(--ink)' }}>
            {data.consensus}
          </p>
        </div>
      )}
    </div>
  )
}
