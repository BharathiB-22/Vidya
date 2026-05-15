"""
Smoke tests for the M05 RAG Q&A service (STEP-10).

Coverage:
  - Pure helpers: _build_context, _deduplicate_sources
  - Qdrant search: tenant + package_id filter applied, correct collection
  - Full ask_package_question: new session creation, session reuse,
    USER+ASSISTANT messages saved, response fields
  - Gemini → Groq quota fallback
  - Non-quota AI error propagates as RagAIError
  - Embedder failure raises RagServiceError
  - Empty Qdrant results still generate an answer
  - Invalid session_id raises RagServiceError

No real Qdrant, database, or network calls.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from app.modules.m05_learning_materials.rag_service import (
    RagAIError,
    RagServiceError,
    _build_context,
    _deduplicate_sources,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENANT_SCHEMA = "tenant_abc"
PACKAGE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
STUDENT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
SESSION_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
ITEM_ID_1 = uuid.UUID("11111111-1111-1111-1111-111111111111")
ITEM_ID_2 = uuid.UUID("22222222-2222-2222-2222-222222222222")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hit(
    item_id: uuid.UUID = ITEM_ID_1,
    score: float = 0.9,
    title: str = "Test Paper",
    url: str = "https://example.com",
    snippet: str = "Some content.",
) -> dict:
    return {
        "tenant_schema": TENANT_SCHEMA,
        "package_id": str(PACKAGE_ID),
        "item_id": str(item_id),
        "source_type": "ARXIV",
        "title": title,
        "url": url,
        "text_snippet": snippet,
        "chunk_index": 0,
        "total_chunks": 1,
        "_score": score,
    }


def _make_qdrant_result(hit: dict) -> MagicMock:
    r = MagicMock()
    payload = {k: v for k, v in hit.items() if k != "_score"}
    r.payload = payload
    r.score = hit["_score"]
    return r


def _make_mock_session_obj(session_id: uuid.UUID = SESSION_ID) -> MagicMock:
    s = MagicMock()
    s.id = session_id
    return s


def _make_mock_message(msg_id: uuid.UUID | None = None) -> MagicMock:
    m = MagicMock()
    m.id = msg_id or uuid.uuid4()
    return m


def _make_mock_qdrant(hits: list[dict] | None = None) -> AsyncMock:
    qdrant = AsyncMock()
    results = [_make_qdrant_result(h) for h in (hits or [])]
    qdrant.search = AsyncMock(return_value=results)
    return qdrant


# ---------------------------------------------------------------------------
# Pure-function tests: _build_context
# ---------------------------------------------------------------------------

class TestBuildContext:
    def test_empty_returns_no_context_message(self):
        result = _build_context([])
        assert "No relevant course material" in result

    def test_single_hit_contains_title_and_snippet(self):
        hit = _make_hit(title="Neural Nets 101", snippet="Basics of deep learning.")
        result = _build_context([hit])
        assert "Neural Nets 101" in result
        assert "Basics of deep learning." in result

    def test_numbered_indices_start_at_one(self):
        hits = [_make_hit(item_id=ITEM_ID_1), _make_hit(item_id=ITEM_ID_2)]
        result = _build_context(hits)
        assert "[1]" in result
        assert "[2]" in result

    def test_multiple_hits_separated_by_blank_line(self):
        hits = [_make_hit(item_id=ITEM_ID_1, title="A"), _make_hit(item_id=ITEM_ID_2, title="B")]
        result = _build_context(hits)
        assert "\n\n" in result


# ---------------------------------------------------------------------------
# Pure-function tests: _deduplicate_sources
# ---------------------------------------------------------------------------

class TestDeduplicateSources:
    def test_single_hit_returns_one_source(self):
        sources = _deduplicate_sources([_make_hit()])
        assert len(sources) == 1

    def test_two_different_items_return_two_sources(self):
        hits = [_make_hit(item_id=ITEM_ID_1), _make_hit(item_id=ITEM_ID_2)]
        sources = _deduplicate_sources(hits)
        assert len(sources) == 2

    def test_duplicate_item_id_keeps_highest_score(self):
        low  = _make_hit(item_id=ITEM_ID_1, score=0.5, snippet="Low")
        high = _make_hit(item_id=ITEM_ID_1, score=0.9, snippet="High")
        sources = _deduplicate_sources([low, high])
        assert len(sources) == 1
        assert sources[0]["relevance_score"] == 0.9
        assert sources[0]["snippet"] == "High"

    def test_duplicate_item_id_highest_wins_regardless_of_order(self):
        high = _make_hit(item_id=ITEM_ID_1, score=0.9, snippet="High")
        low  = _make_hit(item_id=ITEM_ID_1, score=0.5, snippet="Low")
        sources = _deduplicate_sources([high, low])
        assert len(sources) == 1
        assert sources[0]["relevance_score"] == 0.9

    def test_empty_input_returns_empty(self):
        assert _deduplicate_sources([]) == []

    def test_snippet_truncated_to_500_chars(self):
        long_snippet = "X" * 600
        hit = _make_hit(snippet=long_snippet)
        sources = _deduplicate_sources([hit])
        assert len(sources[0]["snippet"]) <= 500

    def test_source_contains_required_fields(self):
        sources = _deduplicate_sources([_make_hit()])
        s = sources[0]
        assert "item_id" in s
        assert "title" in s
        assert "url" in s
        assert "snippet" in s
        assert "relevance_score" in s


# ---------------------------------------------------------------------------
# Integration tests: ask_package_question (full pipeline, mocked)
# ---------------------------------------------------------------------------

def _common_patches(
    qdrant_hits: list[dict] | None = None,
    answer: str = "The answer is 42.",
    model: str = "gemini-2.0-flash",
    session_obj: MagicMock | None = None,
    session_id_return: MagicMock | None = None,
    message_objs: list[MagicMock] | None = None,
):
    """Return a list of patch context managers for the full ask pipeline."""
    mock_qdrant = _make_mock_qdrant(qdrant_hits or [_make_hit()])
    mock_session = session_obj or _make_mock_session_obj()
    msg_objs = message_objs or [_make_mock_message(), _make_mock_message()]

    msg_call_counter = {"n": 0}

    async def fake_append_message(**kwargs):
        idx = msg_call_counter["n"]
        msg_call_counter["n"] += 1
        return msg_objs[idx] if idx < len(msg_objs) else _make_mock_message()

    return dict(
        qdrant=mock_qdrant,
        session=mock_session,
        answer=answer,
        model=model,
        fake_append=fake_append_message,
        patches=[
            patch(
                "app.modules.m05_learning_materials.rag_service.get_rag_client",
                return_value=mock_qdrant,
            ),
            patch(
                "app.modules.m05_learning_materials.embedder.embed_texts",
                new=AsyncMock(return_value=[[0.1] * 768]),
            ),
            patch(
                "app.modules.m05_learning_materials.rag_service._gemini_generate",
                new=AsyncMock(return_value=answer),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageQARepository.create_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageQARepository.get_session",
                new=AsyncMock(return_value=mock_session),
            ),
            patch(
                "app.modules.m05_learning_materials.repository.PackageQARepository.append_message",
                new=fake_append_message,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_ask_creates_new_session_when_none():
    ctx = _common_patches()
    mock_create = AsyncMock(return_value=ctx["session"])

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=ctx["qdrant"]),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="Answer.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=mock_create),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="What is ML?",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    mock_create.assert_called_once()
    assert result["session_id"] == ctx["session"].id


@pytest.mark.asyncio
async def test_ask_reuses_existing_session():
    existing = _make_mock_session_obj(SESSION_ID)
    mock_get = AsyncMock(return_value=existing)
    mock_create = AsyncMock()

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([_make_hit()])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="Answer.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=mock_get),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=mock_create),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="Explain gradient descent.",
            tenant_schema=TENANT_SCHEMA,
            session_id=SESSION_ID,
            db=AsyncMock(),
        )

    mock_get.assert_called_once()
    mock_create.assert_not_called()
    assert result["session_id"] == SESSION_ID


@pytest.mark.asyncio
async def test_ask_saves_user_and_assistant_messages():
    session = _make_mock_session_obj()
    msg_user = _make_mock_message()
    msg_asst = _make_mock_message()

    calls: list[dict] = []

    async def capture_append(**kwargs):
        calls.append(kwargs)
        return msg_user if len(calls) == 1 else msg_asst

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([_make_hit()])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="Answer.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=capture_append),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="What is a neural network?",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    assert len(calls) == 2
    from app.modules.m05_learning_materials.models import QARole
    assert calls[0]["role"] == QARole.USER
    assert calls[0]["content"] == "What is a neural network?"
    assert calls[1]["role"] == QARole.ASSISTANT
    assert calls[1]["content"] == "Answer."


@pytest.mark.asyncio
async def test_ask_response_contains_required_fields():
    session = _make_mock_session_obj()
    msg_asst = _make_mock_message()
    call_idx = {"n": 0}

    async def mock_append(**kw):
        call_idx["n"] += 1
        return _make_mock_message() if call_idx["n"] == 1 else msg_asst

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([_make_hit()])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="The answer.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=mock_append),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="Explain backprop.",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    assert result["answer"] == "The answer."
    assert result["session_id"] == session.id
    assert result["message_id"] == msg_asst.id
    assert isinstance(result["sources"], list)
    assert result["model_used"] is not None


@pytest.mark.asyncio
async def test_search_qdrant_applies_tenant_and_package_filters():
    """Qdrant.search must be called with Filter containing tenant_schema and package_id."""
    session = _make_mock_session_obj()
    mock_qdrant = _make_mock_qdrant([_make_hit()])

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=mock_qdrant),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="OK.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="Question?",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    search_call = mock_qdrant.search.call_args
    assert search_call is not None

    filter_obj = search_call.kwargs["query_filter"]
    conditions = filter_obj.must
    keys = [c.key for c in conditions]
    assert "tenant_schema" in keys
    assert "package_id" in keys

    tenant_cond = next(c for c in conditions if c.key == "tenant_schema")
    package_cond = next(c for c in conditions if c.key == "package_id")
    assert tenant_cond.match.value == TENANT_SCHEMA
    assert package_cond.match.value == str(PACKAGE_ID)


@pytest.mark.asyncio
async def test_search_qdrant_uses_m05_rag_collection():
    session = _make_mock_session_obj()
    mock_qdrant = _make_mock_qdrant([_make_hit()])

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=mock_qdrant),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="OK.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="Question?",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    assert mock_qdrant.search.call_args.kwargs["collection_name"] == "m05_rag"


@pytest.mark.asyncio
async def test_gemini_quota_error_falls_back_to_groq():
    session = _make_mock_session_obj()
    mock_groq = AsyncMock(return_value="Groq answer.")

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([_make_hit()])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch(
            "app.modules.m05_learning_materials.rag_service._gemini_generate",
            new=AsyncMock(side_effect=Exception("resource_exhausted: quota exceeded")),
        ),
        patch("app.modules.m05_learning_materials.rag_service._groq_generate", new=mock_groq),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="What is backprop?",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    mock_groq.assert_called_once()
    assert result["answer"] == "Groq answer."


@pytest.mark.asyncio
async def test_non_quota_gemini_error_raises_rag_ai_error():
    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([_make_hit()])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch(
            "app.modules.m05_learning_materials.rag_service._gemini_generate",
            new=AsyncMock(side_effect=Exception("Internal server error")),
        ),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        with pytest.raises(RagAIError):
            await ask_package_question(
                package_id=PACKAGE_ID,
                student_user_id=STUDENT_ID,
                question="What is a tensor?",
                tenant_schema=TENANT_SCHEMA,
                session_id=None,
                db=AsyncMock(),
            )


@pytest.mark.asyncio
async def test_embedder_error_raises_rag_service_error():
    from app.modules.m05_learning_materials.embedder import EmbedderError

    with (
        patch(
            "app.modules.m05_learning_materials.embedder.embed_texts",
            new=AsyncMock(side_effect=EmbedderError("Provider down")),
        ),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        with pytest.raises(RagServiceError, match="Failed to embed question"):
            await ask_package_question(
                package_id=PACKAGE_ID,
                student_user_id=STUDENT_ID,
                question="Explain SVM.",
                tenant_schema=TENANT_SCHEMA,
                session_id=None,
                db=AsyncMock(),
            )


@pytest.mark.asyncio
async def test_empty_qdrant_results_still_generates_answer():
    """No Qdrant hits → context says 'no relevant material'; answer still generated."""
    session = _make_mock_session_obj()

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="No info available.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="What is X?",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    assert result["answer"] == "No info available."
    assert result["sources"] == []


@pytest.mark.asyncio
async def test_invalid_session_id_raises_rag_service_error():
    """Providing a session_id that does not exist raises RagServiceError."""
    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([_make_hit()])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="Answer.")),
        patch(
            "app.modules.m05_learning_materials.repository.PackageQARepository.get_session",
            new=AsyncMock(return_value=None),
        ),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        with pytest.raises(RagServiceError, match="not found"):
            await ask_package_question(
                package_id=PACKAGE_ID,
                student_user_id=STUDENT_ID,
                question="What is ML?",
                tenant_schema=TENANT_SCHEMA,
                session_id=SESSION_ID,
                db=AsyncMock(),
            )


@pytest.mark.asyncio
async def test_sources_contain_item_id_title_url_snippet():
    """Every source in the result must have the required RAGSourceCitation fields."""
    hit = _make_hit(item_id=ITEM_ID_1, title="Lecture Notes", url="https://u.edu/notes", snippet="Key concept here.")
    session = _make_mock_session_obj()

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([hit])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="Answer.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="Explain the concept.",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    assert len(result["sources"]) == 1
    src = result["sources"][0]
    assert src["item_id"] == str(ITEM_ID_1)
    assert src["title"] == "Lecture Notes"
    assert src["url"] == "https://u.edu/notes"
    assert "Key concept" in src["snippet"]


@pytest.mark.asyncio
async def test_multiple_chunks_same_item_deduplicated_to_one_source():
    """Two hits from the same item_id must produce exactly one source citation."""
    hit_low  = _make_hit(item_id=ITEM_ID_1, score=0.6, snippet="Chunk A.")
    hit_high = _make_hit(item_id=ITEM_ID_1, score=0.95, snippet="Chunk B.")
    session = _make_mock_session_obj()

    with (
        patch("app.modules.m05_learning_materials.rag_service.get_rag_client", return_value=_make_mock_qdrant([hit_low, hit_high])),
        patch("app.modules.m05_learning_materials.embedder.embed_texts", new=AsyncMock(return_value=[[0.1] * 768])),
        patch("app.modules.m05_learning_materials.rag_service._gemini_generate", new=AsyncMock(return_value="Answer.")),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.create_session", new=AsyncMock(return_value=session)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.get_session", new=AsyncMock(return_value=None)),
        patch("app.modules.m05_learning_materials.repository.PackageQARepository.append_message", new=AsyncMock(return_value=_make_mock_message())),
    ):
        from app.modules.m05_learning_materials.rag_service import ask_package_question
        result = await ask_package_question(
            package_id=PACKAGE_ID,
            student_user_id=STUDENT_ID,
            question="Explain.",
            tenant_schema=TENANT_SCHEMA,
            session_id=None,
            db=AsyncMock(),
        )

    assert len(result["sources"]) == 1
    assert result["sources"][0]["relevance_score"] == 0.95
