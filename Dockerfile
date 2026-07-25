# syntax=docker/dockerfile:1

# ---- Stage 1: build the React (Vite) frontend ----
FROM node:20-slim AS frontend
WORKDIR /fe
# The lockfile is maintained with npm 11 (see package.json engines). The npm 10
# bundled with node:20 computes a different optional-dependency tree and fails
# `npm ci` with "Missing: @emnapi/... from lock file" — so the builder must run
# the same npm major as the machines that write the lockfile.
RUN npm install -g npm@11
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
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
