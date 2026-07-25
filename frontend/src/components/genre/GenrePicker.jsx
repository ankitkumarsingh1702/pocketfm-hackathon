/**
 * Genre selection, as a real radio group.
 *
 * Native inputs (visually hidden, not `display:none`) so arrow keys move
 * between options and screen readers announce the group — a row of buttons
 * would lose both. The selected pack's premise, pacing, and taboo moves are
 * shown below, because the choice is not obvious from a one-word label.
 */
export default function GenrePicker({ genres, value, onChange, disabled = false, error }) {
  if (error) {
    return (
      <div
        role="alert"
        style={{
          padding: '14px 16px',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          fontSize: 14,
          color: 'var(--muted)',
        }}
      >
        Could not load the genre packs. {error}
      </div>
    )
  }

  if (!genres.length) {
    return (
      <div style={{ fontSize: 14, color: 'var(--muted)' }} aria-live="polite">
        Loading genres…
      </div>
    )
  }

  const selected = genres.find((g) => g.name === value)

  return (
    <fieldset style={{ border: 'none', display: 'flex', flexDirection: 'column', gap: 14 }}>
      <legend className="label-upper" style={{ fontSize: 11, marginBottom: 2 }}>
        Target genre
      </legend>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {genres.map((pack) => {
          const isSelected = pack.name === value
          return (
            <label
              key={pack.name}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                minHeight: 44,
                padding: '0 18px',
                borderRadius: 'var(--radius-pill)',
                border: `1px solid ${isSelected ? 'var(--accent-line)' : 'var(--border)'}`,
                background: isSelected ? 'var(--accent-soft)' : 'var(--canvas)',
                color: isSelected ? 'var(--accent-text-sm)' : 'var(--ink)',
                fontSize: 14,
                fontWeight: isSelected ? 600 : 500,
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.55 : 1,
                textTransform: 'capitalize',
                transition: 'background var(--dur-fast) var(--ease-standard)',
              }}
            >
              <input
                type="radio"
                name="sgc-genre"
                value={pack.name}
                checked={isSelected}
                disabled={disabled}
                onChange={() => onChange(pack.name)}
                style={{
                  position: 'absolute',
                  width: 1,
                  height: 1,
                  opacity: 0,
                  pointerEvents: 'none',
                }}
              />
              {/* Selection is not carried by colour alone. */}
              <span aria-hidden="true" style={{ marginRight: 8, fontWeight: 700 }}>
                {isSelected ? '✓' : '+'}
              </span>
              {pack.name}
            </label>
          )
        })}
      </div>

      {selected && (
        <div
          style={{
            borderLeft: '2px solid var(--accent-line)',
            paddingLeft: 16,
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
            maxWidth: '68ch',
          }}
        >
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: 'var(--ink)' }}>
            {selected.premise}
          </p>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: 'var(--muted)' }}>
            <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>Pacing. </strong>
            {selected.pacing}
          </p>
          {selected.taboo_moves?.length > 0 && (
            <div>
              <div className="label-upper" style={{ fontSize: 11, marginBottom: 6 }}>
                Never does
              </div>
              <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--muted)' }}>
                {selected.taboo_moves.map((move) => (
                  <li key={move} style={{ fontSize: 14, lineHeight: 1.6 }}>
                    {move}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </fieldset>
  )
}
