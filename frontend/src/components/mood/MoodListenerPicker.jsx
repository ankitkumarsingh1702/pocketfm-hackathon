/**
 * Listener picker — a DEMO affordance, not a product surface.
 *
 * Real listeners never choose who they are; in production this comes from auth
 * and this control does not exist. It sits inline with the query rather than on
 * its own screen for one reason: a separate picker would force you to retype the
 * query for each listener, which destroys the only comparison worth showing —
 * type once, switch listener, watch the same query re-rank.
 *
 * A real radio group, so arrow keys move between listeners and the grouping is
 * announced. A row of buttons would lose both.
 */
export default function MoodListenerPicker({
  profiles,
  value,
  onChange,
  disabled = false,
}) {
  if (!profiles.length) return null

  const options = [
    { id: null, label: 'Anyone', sub: 'no history' },
    ...profiles.map((p) => ({
      id: p.persona_id,
      label: p.display_name,
      sub: `${p.slot} · ${p.history_count} watched`,
    })),
  ]

  return (
    <fieldset style={{ border: 'none', display: 'flex', flexDirection: 'column', gap: 10 }}>
      <legend className="label-upper" style={{ fontSize: 11, marginBottom: 2 }}>
        Listening as
      </legend>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--muted)', maxWidth: '64ch' }}>
        A demo control. Switching listener re-runs the same query — history only
        breaks ties, and it never re-serves a series they already finished.
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {options.map((option) => {
          const isSelected = value === option.id
          return (
            <label
              key={option.id ?? 'anon'}
              style={{
                display: 'inline-flex',
                flexDirection: 'column',
                justifyContent: 'center',
                minHeight: 44,
                padding: '6px 16px',
                borderRadius: 'var(--radius-pill)',
                border: `1px solid ${isSelected ? 'var(--accent-line)' : 'var(--border)'}`,
                background: isSelected ? 'var(--accent-soft)' : 'var(--canvas)',
                color: isSelected ? 'var(--accent-text-sm)' : 'var(--ink)',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.55 : 1,
                transition: 'background var(--dur-fast) var(--ease-standard)',
              }}
            >
              <input
                type="radio"
                name="mood-listener"
                checked={isSelected}
                disabled={disabled}
                onChange={() => onChange(option.id)}
                style={{
                  position: 'absolute',
                  width: 1,
                  height: 1,
                  opacity: 0,
                  pointerEvents: 'none',
                }}
              />
              <span style={{ fontSize: 14, fontWeight: isSelected ? 600 : 500 }}>
                {/* Selection is never carried by colour alone. */}
                <span aria-hidden="true" style={{ marginRight: 7, fontWeight: 700 }}>
                  {isSelected ? '✓' : '+'}
                </span>
                {option.label}
              </span>
              {option.sub && (
                <span style={{ fontSize: 11.5, opacity: 0.8, paddingLeft: 20 }}>
                  {option.sub}
                </span>
              )}
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
