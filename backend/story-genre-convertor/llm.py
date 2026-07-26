"""The single place the Gemini API is touched.

Both stages want the same thing: send a system instruction plus a prompt, get
back a validated Pydantic object. Keeping that in one function means the model
id, the retry policy, and the failure messages are configured once.

Auth: Gemini on Vertex AI via Application Default Credentials, the same setup
the rest of this repo uses (see ../app/llm/gemini_vertex.py). No API keys live
here. Run once:  gcloud auth application-default login

Config: GOOGLE_CLOUD_PROJECT, VERTEX_LOCATION, GEMINI_MODEL — all optional, and
the defaults below match backend/.env.example.
"""

import os
import random
import time
from functools import lru_cache
from typing import Optional, Type, TypeVar

from google import genai
from google.auth import exceptions as auth_errors
from google.genai import errors, types
from pydantic import BaseModel

# Same knobs as backend/app/config.py, read straight from the environment so
# this CLI stays a standalone script rather than importing the FastAPI app.
PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "pocketfm-hackathon")
# "global" is where this project's gemini-3.x IDs are served (us-central1 only has
# the 2.5 family and 404s on 3.x). Keep the default aligned with the studio.
LOCATION = os.environ.get("VERTEX_LOCATION", "global")

# gemini-3.5-flash on "global" — the same model the studio runs everywhere. Fast
# and reliable for the extraction/judging reasoning calls here.
# Point GEMINI_MODEL at something else without touching code (confirm it resolves
# on LOCATION first — a wrong ID 404s on every call).
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

# Both calls here are analysis, not creative writing: the same story must
# decompose the same way twice, or calibrate.py's ceiling check ends up
# measuring sampling noise instead of extractor quality. Deliberately NOT named
# TEMPERATURE — the app's own .env one directory up sets that to 0.9 for
# persona variety, and sourcing it must not silently loosen extraction.
SKELETON_TEMPERATURE = float(os.environ.get("SKELETON_TEMPERATURE", "0"))

# Rate limits, and nothing else, are retried. verify.py issues its ballots
# concurrently now, so six requests can land where one used to; a 429 that was
# nearly impossible against a serial caller is merely unlikely against this one,
# and losing a six-minute job to a few seconds of congestion is the worse
# outcome by far. A 401 or a 404 will not come good on a second attempt, so
# they still fail immediately.
RATE_LIMIT_RETRIES = int(os.environ.get("RATE_LIMIT_RETRIES", "4"))
RATE_LIMIT_BACKOFF = float(os.environ.get("RATE_LIMIT_BACKOFF", "2.0"))

T = TypeVar("T", bound=BaseModel)

ADC_HINT = (
    "No Google Cloud credentials found. This tool reaches Gemini through Vertex "
    "AI using Application Default Credentials — there is no API key to set. "
    "Run once:  gcloud auth application-default login\n"
    f"Then check the project is right (currently {PROJECT!r}) — override it with "
    "GOOGLE_CLOUD_PROJECT if not."
)


@lru_cache(maxsize=1)
def client() -> "genai.Client":
    """Lazily constructed so these modules import fine with no credentials set."""
    try:
        return genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    except auth_errors.DefaultCredentialsError as exc:
        raise RuntimeError(ADC_HINT) from exc


def _translate(exc: errors.ClientError) -> Exception:
    """Turn a Vertex client error into something the reader can act on.

    Returns the exception to raise. Anything unrecognised comes back unchanged,
    so an unexpected code surfaces with its own message rather than a guess.
    """
    # A quota 429 and a rate-limit 429 read identically unless you look at
    # the message, and the two want opposite responses (raise quota vs wait).
    if exc.code == 429:
        return RuntimeError(
            f"Vertex AI rate-limited or quota-capped {MODEL} in {LOCATION}, and it did "
            f"not clear across {RATE_LIMIT_RETRIES} retries. Wait and re-run — "
            "calibrate.py caches completed extractions in .cache/, so a re-run resumes "
            "rather than restarts. If it persists, request more quota, move "
            "VERTEX_LOCATION to another region, or lower VERIFY_CONCURRENCY."
        )
    if exc.code in (401, 403):
        return RuntimeError(
            f"Vertex AI rejected the credentials (HTTP {exc.code}) for project "
            f"{PROJECT!r}. Refresh ADC (gcloud auth application-default login), and "
            "check the account has the Vertex AI User role and that "
            "aiplatform.googleapis.com is enabled — ../../scripts/gcp_setup.sh does "
            "the last two."
        )
    if exc.code == 404:
        return RuntimeError(
            f"Vertex AI serves no model {MODEL!r} in {LOCATION!r}. Set GEMINI_MODEL "
            "to a model available there, or move VERTEX_LOCATION to a region that "
            "carries it."
        )
    return exc


def structured(
    system: str,
    prompt: str,
    schema: Type[T],
    max_output_tokens: int = 16000,
    temperature: Optional[float] = None,
) -> T:
    """One call, returning a validated instance of `schema`.

    `temperature` defaults to SKELETON_TEMPERATURE. Analysis callers (extraction,
    alignment) want that 0; the transform stage is creative writing and passes
    its own, so the two never have to share a setting.

    Retries on 429 and on nothing else — see RATE_LIMIT_RETRIES. Safe to call
    from several threads at once: verify.py does, and the only shared state is
    the client, which the SDK supports using concurrently.

    Raises with a readable message rather than returning None, because every
    caller in this pipeline treats a missing skeleton as fatal anyway.
    """
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=SKELETON_TEMPERATURE if temperature is None else temperature,
        response_mime_type="application/json",
        response_schema=schema,
        max_output_tokens=max_output_tokens,
    )

    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            response = client().models.generate_content(
                model=MODEL, contents=prompt, config=config
            )
            break
        except auth_errors.DefaultCredentialsError as exc:
            # Credentials can fail to resolve on first use rather than at client
            # construction, so the same hint has to live on both paths.
            raise RuntimeError(ADC_HINT) from exc
        except errors.ClientError as exc:
            if exc.code != 429 or attempt == RATE_LIMIT_RETRIES:
                translated = _translate(exc)
                if translated is exc:
                    raise
                raise translated from exc
            # Jittered, so a set of ballots rate-limited together does not come
            # back in lockstep and recreate the burst that caused it.
            time.sleep(RATE_LIMIT_BACKOFF * (2**attempt) + random.uniform(0, 1))

    parsed = response.parsed
    if isinstance(parsed, schema):
        return parsed

    # Work out why, so the failure is actionable instead of a bare None.
    reason = "unknown"
    if response.candidates:
        finish = response.candidates[0].finish_reason
        reason = getattr(finish, "name", str(finish))
    elif response.prompt_feedback is not None:
        reason = f"prompt blocked ({response.prompt_feedback})"

    hint = ""
    if reason == "MAX_TOKENS":
        hint = (
            " The JSON was cut off mid-object. Raise max_output_tokens, or the story "
            "is producing more beats than the budget allows."
        )
    elif reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"}:
        hint = " The story tripped a safety filter — try a different source text."

    raise RuntimeError(
        f"{MODEL} returned no parsable {schema.__name__} (finish_reason={reason}).{hint}"
    )
