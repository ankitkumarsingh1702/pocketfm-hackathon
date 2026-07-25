import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

import { SGC_TARGET, SGC_TOKEN } from './sgc-token.js'

// Simulated Studio backend on Cloud Run. Public (allUsers invoker), so it needs
// no credential — unlike the genre converter below. Point STUDIO_TARGET at
// http://localhost:8000 to develop against a local `uv run uvicorn app.main:app`.
const STUDIO_TARGET = process.env.VITE_STUDIO_TARGET
  || 'https://simulated-studio-v4c7wg52ia-uc.a.run.app'

const studioProxy = { target: STUDIO_TARGET, changeOrigin: true }

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Simulated Studio backend.
      '/api': studioProxy,
      '/health': studioProxy,

      // Story genre converter, on Cloud Run. The service has no public invoker
      // binding, so the bearer token is attached here — server-side, on the way
      // out — rather than in the browser. Requests leave the page as same-origin
      // `/sgc/*`, which means no CORS preflight, which is the only reason this
      // works at all: a preflight OPTIONS carries no Authorization header and
      // Cloud Run would 403 it. See sgc-token.js.
      '/sgc': {
        target: SGC_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sgc/, ''),
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Authorization', `Bearer ${SGC_TOKEN}`)
          })
          // A 403 here is almost always an expired token (they last ~1 hour).
          // Say so in the terminal rather than letting the UI report a bare 403.
          proxy.on('proxyRes', (proxyRes, req) => {
            if (proxyRes.statusCode === 401 || proxyRes.statusCode === 403) {
              console.error(
                `[sgc] ${proxyRes.statusCode} on ${req.url} — the identity token has ` +
                  'likely expired. Refresh it with: npm run sgc:token',
              )
            }
          })
        },
      },
    },
  },
})
