# syntax=docker/dockerfile:1
#
# Standalone service. Built from this directory, not the repo root — the genre
# converter shares nothing with the Simulated Studio backend except a project.

FROM python:3.12-slim

WORKDIR /srv

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY genres/ ./genres/
COPY stories/ ./stories/

# Cloud Run's filesystem is in-memory; keep cache writes off the app directory
# so they are obviously ephemeral rather than looking like state.
ENV CACHE_DIR=/tmp/sgc-cache
ENV PORT=8080
EXPOSE 8080

# One worker on purpose: jobs are tracked in a process-local dict, so a second
# worker would answer polls for jobs it has never heard of.
CMD ["sh", "-c", "exec uvicorn api:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
