/**
 * Primary/secondary/ghost button. Presentation only — behaviour comes from the
 * `onClick` handler the caller passes down.
 */
export default function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  onClick,
  type = 'button',
}) {
  const pad = size === 'sm' ? '8px 14px' : '12px 20px'
  const fontSize = size === 'sm' ? 13 : 15

  const base = {
    fontFamily: 'var(--font-sans)',
    fontWeight: 600,
    fontSize,
    borderRadius: 'var(--radius-sm)',
    padding: pad,
    cursor: disabled ? 'not-allowed' : 'pointer',
    border: '1px solid transparent',
    transition:
      'background var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
    opacity: disabled ? 0.5 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    gap: 8,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  }
  const variants = {
    primary: { background: 'var(--accent)', color: '#fff' },
    secondary: {
      background: 'var(--surface-raised)',
      color: 'var(--ink)',
      border: '1px solid var(--border)',
    },
    ghost: { background: 'transparent', color: 'var(--ink)' },
  }

  const setBg = (bg) => (e) => {
    if (!disabled && variant === 'primary') e.currentTarget.style.background = bg
  }

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      style={{ ...base, ...variants[variant] }}
      onMouseEnter={setBg('var(--accent-press)')}
      onMouseLeave={setBg('var(--accent)')}
    >
      {children}
    </button>
  )
}
