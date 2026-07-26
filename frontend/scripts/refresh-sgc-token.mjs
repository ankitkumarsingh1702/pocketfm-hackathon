#!/usr/bin/env node
/**
 * Refresh the hardcoded Cloud Run identity token in sgc-token.js.
 *
 * Google identity tokens last about an hour, so the token committed in
 * sgc-token.js goes stale between working sessions. This mints a fresh one from
 * whatever account gcloud is currently logged in as and rewrites the constant
 * in place, leaving the surrounding documentation untouched.
 *
 *     npm run sgc:token
 *
 * Restart `npm run dev` afterwards — Vite reads the token once, at config load.
 */

import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const TOKEN_FILE = join(dirname(dirname(fileURLToPath(import.meta.url))), 'sgc-token.js')

let token
try {
  token = execFileSync('gcloud', ['auth', 'print-identity-token'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim()
} catch (err) {
  console.error('Could not mint an identity token from gcloud.')
  console.error(err.stderr?.toString().trim() || err.message)
  console.error('\nLog in first:  gcloud auth login')
  process.exit(1)
}

if (!token.startsWith('ey')) {
  console.error('gcloud returned something that is not a JWT. Refusing to write it.')
  process.exit(1)
}

const source = readFileSync(TOKEN_FILE, 'utf8')
const updated = source.replace(
  /(export const SGC_TOKEN =\s*\n\s*')[^']*(')/,
  (_match, head, tail) => `${head}${token}${tail}`,
)

if (updated === source) {
  console.error(`Could not find the SGC_TOKEN constant in ${TOKEN_FILE}. Not modified.`)
  process.exit(1)
}

writeFileSync(TOKEN_FILE, updated)

// Report the expiry so it is obvious how long this is good for.
const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'))
const expires = new Date(payload.exp * 1000)
console.log(`Wrote a fresh token to sgc-token.js (${payload.email}).`)
console.log(`Valid until ${expires.toLocaleTimeString()}. Restart the dev server to pick it up.`)
