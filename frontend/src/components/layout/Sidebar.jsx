import { NavLink } from 'react-router-dom'

import { AUDIENCE_ARMY, LENSES, UPCOMING_SUPERPOWERS } from '../../config/constants'
import { formatInt } from '../../utils/format'
import { Icon, Wordmark } from '../primitives'
import HealthBadge from '../HealthBadge'

/**
 * Studio navigation rail. One `NavLink` per lens — the route, not component
 * state, decides which is active, so the current lens survives a reload and
 * can be linked to directly. On small screens the shell shows this as an
 * off-canvas drawer via the `open` class; `onNavigate` lets the shell close
 * that drawer when a link is chosen.
 */
export default function Sidebar({ open = false, health, onNavigate }) {
  return (
    <aside className={`sidebar${open ? ' is-open' : ''}`} aria-label="Studio navigation">
      <Wordmark size={19} />

      <nav className="side-nav" aria-label="Lenses">
        <div className="side-nav__label label-upper" style={{ fontSize: 11 }}>
          Lenses
        </div>
        {LENSES.map((lens) => (
          <NavLink
            key={lens.id}
            to={lens.path}
            className={({ isActive }) => `side-link${isActive ? ' is-active' : ''}`}
            onClick={onNavigate}
          >
            <span className="side-link__icon">
              <Icon name={lens.icon} />
            </span>
            {lens.label}
          </NavLink>
        ))}
      </nav>

      <div className="side-soon">
        <div className="side-nav__label label-upper" style={{ fontSize: 11 }}>
          Coming soon
        </div>
        {UPCOMING_SUPERPOWERS.map((name) => (
          <span key={name} className="side-soon__item">
            <span className="side-soon__dot" aria-hidden="true" />
            {name}
          </span>
        ))}
      </div>

      <div className="sidebar__foot">
        <HealthBadge {...health} />
        <span className="sidebar__foot-line">
          Panel of {formatInt(AUDIENCE_ARMY)} simulated listeners · persona simulation on Google
          Vertex AI
        </span>
      </div>
    </aside>
  )
}
