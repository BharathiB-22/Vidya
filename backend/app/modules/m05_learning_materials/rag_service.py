"""
M05 Learning Material Packager — RAG Q&A service (STEP-10).

Public surface:
  RagServiceError          raised for non-recoverable RAG failures
  RagAIError               raised when the AI provider fails answer generation
  ask_package_question()   main entry point: embed → search → generate → save
  get_rag_client()         lazy AsyncQdrantClient singleton

Flow
----
  1. Embed the student question via embed_texts() (text-embedding-004).
  2. Search Qdrant collection "m05_rag" filtered to tenant_schema + package_id.
  3. Build a numbered prompt context from the top-K retrieved chunks.
  4. Generate answer via Gemini Flash (primary) or Groq (quota-only fallback).
  5. Deduplicate sources by item_id; keep the highest-scoring chunk per item.
  6. Get-or-create a Q&A session; append USER then ASSISTANT messages.
  7. Return a dict compatible with RAGAnswerResponse.

Boundaries (STEP-10 only):
  - No router endpoints
  - No package-level service orchestration
  - No frontend or notebook chat
  - Audit logging is delegated to the STEP-11 service layer

Deferred imports:
  google-genai, openai, qdrant_client are imported inside async functions so
  the module loads cleanly in tests that mock those dependencies.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("vidya.m05.rag_service")

_QDRANT_COLLECTION = "m05_rag"
_qdrant_client = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class RagServiceError(Exception):
    """Non-recoverable RAG service failure (missing session, Qdrant down, etc.)."""


class RagAIError(Exception):
    """AI provider failed during answer generation."""


# ---------------------------------------------------------------------------
# Qdrant client singleton
# ---------------------------------------------------------------------------

def get_rag_client() -> Any:
    """Return a lazily-initialised AsyncQdrantClient (deferred import)."""
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import AsyncQdrantClient
        from app.config import settings
        kwargs: dict[str, Any] = {"url": settings.QDRANT_URL}
        if settings.QDRANT_API_KEY:
            kwargs["api_key"] = settings.QDRANT_API_KEY
        _qdrant_client = AsyncQdrantClient(**kwargs)
    return _qdrant_client


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def ask_package_question(
    package_id: UUID,
    student_user_id: UUID,
    question: str,
    tenant_schema: str,
    session_id: UUID | None,
    *,
    db: AsyncSession,
) -> dict[str, Any]:
    """Embed question, search Qdrant, generate answer, persist messages.

    Returns a dict with keys: session_id, message_id, answer, sources, model_used.
    Compatible with the RAGAnswerResponse schema.
    """
    from app.config import settings
    from app.modules.m05_learning_materials.embedder import EmbedderError, embed_texts
    from app.modules.m05_learning_materials.models import QARole
    from app.modules.m05_learning_materials.repository import PackageQARepository

    _log_extra = {
        "tenant_schema": tenant_schema,
        "package_id": str(package_id),
    }

    # ------------------------------------------------------------------
    # 1. Embed question
    # ------------------------------------------------------------------
    try:
        q_vectors = await embed_texts(
            [question],
            tenant_schema=tenant_schema,
            package_id=str(package_id),
        )
    except EmbedderError as exc:
        raise RagServiceError(f"Failed to embed question: {exc}") from exc

    # ------------------------------------------------------------------
    # 2. Search Qdrant
    # ------------------------------------------------------------------
    search_hits = await _search_qdrant(
        question_vector=q_vectors[0],
        package_id=package_id,
        tenant_schema=tenant_schema,
        top_k=settings.M05_RAG_TOP_K,
    )

    logger.info(
        "m05.rag: retrieved %d chunk(s) for package %s",
        len(search_hits), package_id,
        extra=_log_extra,
    )

    # ------------------------------------------------------------------
    # 3. Build context and deduplicate sources
    # ------------------------------------------------------------------
    context_text = _build_context(search_hits)
    sources = _deduplicate_sources(search_hits)

    # ------------------------------------------------------------------
    # 4. Generate answer
    # ------------------------------------------------------------------
    answer, model_used = await _generate_answer(question, context_text)

    logger.info(
        "m05.rag: answer generated (model=%s sources=%d)",
        model_used, len(sources),
        extra=_log_extra,
    )

    # ------------------------------------------------------------------
    # 5. Get or create Q&A session
    # ------------------------------------------------------------------
    qa_session = await _get_or_create_session(
        package_id=package_id,
        student_user_id=student_user_id,
        session_id=session_id,
        db=db,
    )

    # ------------------------------------------------------------------
    # 6. Persist messages
    # ------------------------------------------------------------------
    await PackageQARepository.append_message(
        session_id=qa_session.id,
        role=QARole.USER,
        content=question,
        db=db,
    )

    sources_dicts = [_source_to_dict(s) for s in sources]
    assistant_msg = await PackageQARepository.append_message(
        session_id=qa_session.id,
        role=QARole.ASSISTANT,
        content=answer,
        sources=sources_dicts,
        db=db,
    )

    return {
        "session_id": qa_session.id,
        "message_id": assistant_msg.id,
        "answer": answer,
        "sources": sources,
        "model_used": model_used,
    }


# ---------------------------------------------------------------------------
# Qdrant search
# ---------------------------------------------------------------------------

async def _search_qdrant(
    question_vector: list[float],
    package_id: UUID,
    tenant_schema: str,
    top_k: int,
) -> list[dict[str, Any]]:
    """Search m05_rag; return list of payload dicts augmented with '_score'."""
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    qdrant = get_rag_client()
    try:
        results = await qdrant.search(
            collection_name=_QDRANT_COLLECTION,
            query_vector=question_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="tenant_schema",
                        match=MatchValue(value=tenant_schema),
                    ),
                    FieldCondition(
                        key="package_id",
                        match=MatchValue(value=str(package_id)),
                    ),
                ]
            ),
            limit=top_k,
            with_payload=True,
        )
    except Exception as exc:
        raise RagServiceError(f"Qdrant search failed: {exc}") from exc

    return [{**r.payload, "_score": r.score} for r in results]


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context(search_hits: list[dict[str, Any]]) -> str:
    """Format retrieved chunks as a numbered context string for the AI prompt."""
    if not search_hits:
        return "(No relevant course material found for this question.)"

    parts: list[str] = []
    for i, hit in enumerate(search_hits, start=1):
        title   = hit.get("title", "")
        snippet = hit.get("text_snippet", "")
        parts.append(f"[{i}] {title}\n{snippet}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Source deduplication
# ---------------------------------------------------------------------------

def _deduplicate_sources(search_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge chunks by item_id; keep the highest-scoring chunk per item.

    Returns plain dicts compatible with RAGSourceCitation.
    """
    best: dict[str, dict[str, Any]] = {}
    for hit in search_hits:
        item_id = str(hit.get("item_id", ""))
        score   = hit.get("_score", 0.0)
        if item_id not in best or score > best[item_id]["_score"]:
            best[item_id] = hit

    return [
        {
            "item_id":         hit["item_id"],
            "title":           hit.get("title", ""),
            "url":             hit.get("url"),
            "snippet":         hit.get("text_snippet", "")[:500],
            "relevance_score": hit.get("_score"),
        }
        for hit in best.values()
    ]


def _source_to_dict(source: dict[str, Any]) -> dict[str, Any]:
    """Return source dict serialisable for JSONB storage."""
    return {
        "item_id":         str(source["item_id"]),
        "title":           source.get("title", ""),
        "url":             source.get("url"),
        "snippet":         source.get("snippet", ""),
        "relevance_score": source.get("relevance_score"),
    }


# ---------------------------------------------------------------------------
# AI generation — Gemini primary, Groq quota fallback
# ---------------------------------------------------------------------------

_QUOTA_SIGNALS = (
    "resource_exhausted", "429", "quota",
    "rate_limit", "rate limit", "too many requests",
)


def _is_quota_error(exc: Exception) -> bool:
    return any(s in str(exc).lower() for s in _QUOTA_SIGNALS)


def _build_prompt(question: str, context: str) -> tuple[str, str]:
    system = (
        "You are an educational assistant embedded in a university learning platform. "
        "Answer student questions using only the provided course material context. "
        "Do not introduce information outside the given context. "
        "If the context is insufficient, say so clearly."
    )
    user = (
        f"Course Material Context:\n"
        f"---\n"
        f"{context}\n"
        f"---\n\n"
        f"Student Question: {question}\n\n"
        f"Provide a clear, concise answer based on the context above. "
        f"Reference source numbers (e.g. [1], [2]) where applicable."
    )
    return system, user


async def _generate_answer(
    question: str,
    context: str,
) -> tuple[str, str]:
    """Generate plain-text answer. Returns (answer_text, model_name)."""
    from app.config import settings

    system, user = _build_prompt(question, context)

    try:
        answer = await _gemini_generate(system, user)
        return answer, settings.GEMINI_MODEL
    except RagAIError:
        raise
    except Exception as exc:
        if not _is_quota_error(exc):
            raise RagAIError(f"Gemini answer generation failed: {exc}") from exc
        logger.warning(
            "m05.rag: Gemini quota error (%s) — falling back to Groq", exc
        )

    answer = await _groq_generate(system, user)
    return answer, settings.GROQ_MODEL


async def _gemini_generate(system: str, user: str) -> str:
    """Call Gemini Flash and return plain-text answer."""
    from google import genai
    from google.genai import types
    from app.config import settings

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        temperature=0.3,
        system_instruction=system,
    )
    response = await client.aio.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=user,
        config=config,
    )
    text = getattr(response, "text", None)
    if not text:
        raise RagAIError("Gemini returned an empty or blocked response.")
    return text.strip()


async def _groq_generate(system: str, user: str) -> str:
    """Call Groq (OpenAI-compatible) and return plain-text answer."""
    from openai import AsyncOpenAI
    from app.config import settings

    if not settings.GROQ_API_KEY:
        raise RagAIError(
            "GROQ_API_KEY not configured — cannot use Groq fallback."
        )

    client = AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
    response = await client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RagAIError("Groq returned an empty response.")
    return text


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

async def _get_or_create_session(
    package_id: UUID,
    student_user_id: UUID,
    session_id: UUID | None,
    *,
    db: AsyncSession,
):
    """Return an existing Q&A session or create a new one."""
    from app.modules.m05_learning_materials.repository import PackageQARepository

    if session_id is not None:
        session = await PackageQARepository.get_session(session_id, db=db)
        if session is None:
            raise RagServiceError(f"Q&A session {session_id} not found.")
        return session

    return await PackageQARepository.create_session(
        package_id=package_id,
        student_user_id=student_user_id,
        db=db,
    )
