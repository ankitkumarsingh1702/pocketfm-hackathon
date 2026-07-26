# syntax=docker/dockerfile:1

# ---- Stage 1: build the React (Vite) frontend ----
FROM node:20-slim AS frontend
WORKDIR /fe
# Pin the exact npm that generated package-lock.json (via
# `npx -y npm@11.18.0 install --package-lock-only`). npm versions disagree on
# optional platform-dependency subtrees (@emnapi/* under the wasm bindings), and
# macOS npm skips validating other platforms' subtrees — so a lockfile that
# passes `npm ci` locally can still fail here. Regenerate the lockfile with this
# same pinned version, and verify with `npx -y npm@11.18.0 ci --dry-run`.
RUN npm install -g npm@11.18.0
COPY frontend/package.json ./
RUN npm i
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: Python backend (serves the built frontend as static files) ----
FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /srv/backend

# Install backend deps first (better layer caching)
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# App code + persona skills/data. config.py computes REPO_ROOT=<backend>/..
# so backend at /srv/backend => skills at /srv/skills, data at /srv/data.
COPY backend/ ./
COPY skills/ /srv/skills/
COPY data/ /srv/data/

# Built frontend served as static files by FastAPI.
COPY --from=frontend /fe/dist ./static

ENV PORT=8080
EXPOSE 8080

# Shell form (via sh -c + exec) so ${PORT} expands at runtime; Cloud Run injects PORT.
CMD ["sh", "-c", "exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
