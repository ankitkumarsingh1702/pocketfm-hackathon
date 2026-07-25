import { Route, Routes } from 'react-router-dom'

import StudioShell from './pages/StudioShell'

/**
 * Application root. The shell owns every lens route itself (each lens panel
 * stays mounted across navigation), so a single catch-all route hands the
 * whole path space to it; unknown paths redirect from inside the shell.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/*" element={<StudioShell />} />
    </Routes>
  )
}
