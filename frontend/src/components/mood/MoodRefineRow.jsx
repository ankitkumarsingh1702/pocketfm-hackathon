/**
 * Refinement, in mood space.
 *
 * The follow-up to a mood result is "heavier / lighter / slower / warmer", never
 * re-typing the sentence. Each control nudges the shelf's target vector and
 * re-retrieves; no model runs in this path, which is what keeps it instant.
 *
 * The raw slider position is what gets sent, not a pre-nudged set of axes — the
 * engine needs to know WHICH axis was steered in order to grant that axis room
 * against the destination's own bounds. Sending only the destination point made
 * a full drag a no-op once; that bug is why this comment exists.
 */
export default function MoodRefineRow({ shelf, sliders, onRefine, busy = false }) {
  if (!sliders.length) return null

  return (
    <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="label-upper" style={{ fontSize: 11 }}>
        Nudge this shelf
      </div>

      <div
        role="group"
        aria-label={`Refine ${shelf.label}`}
        style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}
      >
        {sliders.map((slider) =>
          [
            [-1, slider.left],
            [1, slider.right],
          ].map(([value, label]) => (
            <button
              key={`${slider.id}:${value}`}
              type="button"
              onClick={() => onRefine(shelf, { [slider.id]: value })}
              disabled={busy}
              style={{
                minHeight: 44,
                whiteSpace: 'nowrap',
                background: 'var(--canvas)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-pill)',
                color: 'var(--ink)',
                padding: '0 16px',
                fontFamily: 'var(--font-sans)',
                fontSize: 13.5,
                cursor: busy ? 'not-allowed' : 'pointer',
                opacity: busy ? 0.55 : 1,
                transition: 'background var(--dur-fast) var(--ease-standard)',
              }}
            >
              {label}
            </button>
          )),
        )}
      </div>
    </div>
  )
}
