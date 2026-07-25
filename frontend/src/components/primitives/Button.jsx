/**
 * Primary/secondary/ghost button. Presentation only — behaviour comes from the
 * `onClick` handler the caller passes down. Primary is always black-on-white
 * per the studio's design system; red never carries the main action.
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
    minHeight: size === 'sm' ? 36 : 44,
    cursor: disabled ? 'not-allowed' : 'pointer',
    border: '1px solid transparent',
    transition:
      'background var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard)',
    opacity: disabled ? 0.5 : 1,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    whiteSpace: 'nowrap',
    flexShrink: 0,
  }
  const variants = {
    primary: { background: 'var(--cta)', color: '#fff' },
    // Secondary is the studio's bordered CTA: white surface, black border.
    secondary: {
      background: 'var(--surface-raised)',
      color: 'var(--ink)',
      border: '1px solid var(--ink)',
    },
    ghost: { background: 'transparent', color: 'var(--ink)' },
  }

  const hover = (on) => (e) => {
    if (disabled) return
    if (variant === 'primary') {
      e.currentTarget.style.background = on ? 'var(--cta-hover)' : 'var(--cta)'
    } else if (variant === 'secondary') {
      e.currentTarget.style.background = on ? 'var(--surface)' : 'var(--surface-raised)'
    } else {
      e.currentTarget.style.background = on ? 'var(--surface)' : 'transparent'
    }
  }

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      style={{ ...base, ...variants[variant] }}
      onMouseEnter={hover(true)}
      onMouseLeave={hover(false)}
    >
      {children}
    </button>
  )
}
