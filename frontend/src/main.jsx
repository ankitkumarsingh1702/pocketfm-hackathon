import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Global styles, in cascade order:
//   1. index.css       — single source of truth for design tokens (Lexend +
//                        white / black / soft-red) and base element styles.
//   2. ui-tokens.css   — alias bridge mapping the Writers Room's --ui-* names
//                        onto the shell tokens above (no competing values).
//   3. writers-room.css — Writers Room / Agent Profile component styles.
import './index.css'
import './ui-tokens.css'
import './writers-room.css'
import StudioPage from './pages/StudioPage.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <StudioPage />
  </StrictMode>,
)
