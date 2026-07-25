"""Best-effort Firestore persistence for simulation runs.

Saving is entirely optional: if Firestore is disabled or unavailable (no
credentials, no network, missing database, etc.), ``save_simulation`` logs a
warning and returns ``None`` instead of raising. The engine must keep working
whether or not persistence succeeds.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.schemas import Story

logger = logging.getLogger(__name__)


def save_simulation(kind: str, story: Story, result: dict) -> str | None:
    """Persist a simulation run and return its document id, or ``None``.

    Writes ``{kind, title, episode, created, result}`` to the configured
    collection. Never raises — any failure yields ``None``.
    """
    if not settings.use_firestore:
        return None

    try:
        from google.cloud import firestore

        client = firestore.Client(
            project=settings.google_cloud_project,
            database=settings.firestore_database,
        )
        doc = {
            "kind": kind,
            "title": story.title,
            "episode": story.episode,
            "created": firestore.SERVER_TIMESTAMP,
            "result": result,
        }
        _, ref = client.collection(settings.firestore_collection).add(doc)
        return ref.id
    except Exception as exc:  # noqa: BLE001 — persistence is strictly best-effort
        logger.warning("Firestore save_simulation failed: %s", exc)
        return None
