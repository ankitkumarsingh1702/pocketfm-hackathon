# PocketFM Hackathon

React + Vite (JavaScript) app for the hackathon.

## Getting started

```bash
npm install
npm run dev
```

Scripts: `dev`, `build`, `preview`, `lint`.

## Team workflow (3 devs)

We use a simple two-branch flow. **`develop` is the default branch — all work merges here first.**

- **`main`** — stable / demo-ready. Never push directly.
- **`develop`** — integration branch. **All PRs target `develop`.**

### Day-to-day

1. Always branch off the latest `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b feat/<your-name>/<short-description>
   ```
2. Commit your work and push the branch:
   ```bash
   git push -u origin feat/<your-name>/<short-description>
   ```
3. Open a Pull Request **into `develop`** (it's the default base, so this is automatic):
   ```bash
   gh pr create --base develop --fill
   ```
4. Get **1 review** from another dev, then squash-merge into `develop`.
5. When `develop` is stable (e.g. before the demo), we merge `develop` → `main` via a PR.

### Rules of thumb

- One feature = one branch = one PR. Keep PRs small.
- Never commit directly to `main` or `develop` — always go through a PR.
- Pull `develop` before starting new work to avoid conflicts.
- Branch names: `feat/...`, `fix/...`, `chore/...`.

> Note: This is a private repo on a free plan, so GitHub's automatic branch
> protection isn't available. The rules above are enforced by team convention.
> If we upgrade to GitHub Pro (free via GitHub Education) or make the repo
> public, we can enforce "PR + 1 review required" automatically.

---

## Vite / React notes

This project uses [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react) with [Oxlint](https://oxc.rs).

- **React Compiler** is not enabled by default (impacts dev/build perf). To add it, see the [docs](https://react.dev/learn/react-compiler/installation).
- For a production app, consider the [TypeScript template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) with type-aware lint rules.
