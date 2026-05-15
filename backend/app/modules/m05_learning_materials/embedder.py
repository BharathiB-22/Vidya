"""
M05 Learning Material Packager — Embedding and relevance ranking (STEP-06).

Public surface:
  EmbedderError         raised when the embedding provider fails
  get_embedder_client() returns a google-genai Client (deferred import)
  embed_texts()         batch-embed raw strings; returns parallel float vectors
  cosine_similarity()   cosine similarity clamped to [0.0, 1.0]
  score_items()         embed unit context + RawItem.raw_text; return ranked pairs

Architectural boundaries:
  - No DB writes, no Qdrant writes, no Celery dispatch.
  - The curation Celery task (STEP-08) calls score_items() and persists results.
  - Deferred google-genai import: module loads cleanly without the SDK (same
    pattern as M03 ai_provider.py GeminiCourseKitProvider).
"""
from __future__ import annotations

import logging
import math
from typing import Any

from app.modules.m05_learning_materials.source_adapters.base import RawItem

logger = logging.getLogger("vidya.m05.embedder")

_EMBED_MODEL = "text-embedding-004"


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class EmbedderError(Exception):
    """Raised when the embedding provider fails (wraps API / network errors)."""


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def get_embedder_client() -> Any:
    """Return a configured google-genai Client.

    Deferred import: module remains importable in tests that mock this function
    without requiring google-genai to be installed or configured.
    """
    from google import genai
    from app.config import settings
    return genai.Client(api_key=settings.GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# Low-level: single-batch embed call
# ---------------------------------------------------------------------------

async def _embed_batch(client: Any, texts: list[str]) -> list[list[float]]:
    """Call embed_content for one batch of texts; return parallel float vectors.

    google-genai 2.x: embed_content accepts a list[str] as `contents` and returns
    EmbedContentResponse with .embeddings: list[ContentEmbedding], each having
    .values: list[float].
    """
    response = await client.aio.models.embed_content(
        model=_EMBED_MODEL,
        contents=texts,
    )
    return [list(e.values) for e in response.embeddings]


# ---------------------------------------------------------------------------
# Public: embed_texts
# ---------------------------------------------------------------------------

async def embed_texts(
    texts: list[str],
    *,
    tenant_schema: str,
    package_id: str,
) -> list[list[float]]:
    """Embed a list of texts in batches of settings.M05_EMBED_BATCH_SIZE.

    Returns a list of float vectors parallel to `texts`.
    Raises EmbedderError for any provider failure; no partial results are returned
    so the caller can decide whether to retry or abort the curation task.
    """
    if not texts:
        return []

    from app.config import settings

    batch_size = settings.M05_EMBED_BATCH_SIZE
    log = logging.LoggerAdapter(
        logger,
        extra={"tenant_schema": tenant_schema, "package_id": package_id},
    )

    client = get_embedder_client()
    all_vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        log.info(
            "Embedding batch %d-%d of %d texts",
            start + 1,
            start + len(batch),
            len(texts),
        )
        try:
            vectors = await _embed_batch(client, batch)
        except Exception as exc:
            raise EmbedderError(
                f"Provider error on batch [{start}:{start + len(batch)}]: {exc}"
            ) from exc
        all_vectors.extend(vectors)

    return all_vectors


# ---------------------------------------------------------------------------
# Public: cosine_similarity
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors, clamped to [0.0, 1.0].

    - Returns 0.0 for zero-magnitude vectors (real embeddings are never zero;
      this is a safe fallback for guard-only cases).
    - Clamped to [0.0, 1.0]: for relevance ranking, negative cosine similarity
      means unrelated content — treating it as 0 is semantically correct.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (mag_a * mag_b)))


# ---------------------------------------------------------------------------
# Public: score_items
# ---------------------------------------------------------------------------

async def score_items(
    unit_context: str,
    items: list[RawItem],
    *,
    tenant_schema: str,
    package_id: str,
) -> list[tuple[RawItem, float]]:
    """Embed unit_context and all item raw_text; rank items by cosine similarity.

    Returns (RawItem, score) pairs sorted descending by score.
    Ties broken by item.title ascending — deterministic for equal-score items.
    Scores are guaranteed in [0.0, 1.0] (cosine_similarity clamps).
    """
    if not items:
        return []

    log = logging.LoggerAdapter(
        logger,
        extra={"tenant_schema": tenant_schema, "package_id": package_id},
    )

    # unit_context is prepended so it shares the same batch calls as item texts.
    # Index 0 is the unit vector; indices 1..N are item vectors.
    all_texts = [unit_context] + [item.raw_text for item in items]
    all_vectors = await embed_texts(
        all_texts,
        tenant_schema=tenant_schema,
        package_id=package_id,
    )

    unit_vector  = all_vectors[0]
    item_vectors = all_vectors[1:]

    scored: list[tuple[RawItem, float]] = [
        (item, cosine_similarity(unit_vector, vec))
        for item, vec in zip(items, item_vectors)
    ]

    # Descending relevance; ascending title breaks ties deterministically.
    scored.sort(key=lambda t: (-t[1], t[0].title))

    log.info(
        "Scored %d items: top=%.4f bottom=%.4f",
        len(scored),
        scored[0][1],
        scored[-1][1],
    )
    return scored
