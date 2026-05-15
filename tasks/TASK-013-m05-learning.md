# TASK-013 — M05 Learning Material Packager

**Phase:** 1 — Teach and Prepare
**Module path:** `backend/app/modules/m05_learning_materials/`
**Stack:** Python 3.12, FastAPI, Celery, Qdrant, Google text-embedding-004, PostgreSQL 16

---

## PRD Reference

F-04: Learning Material Packager — `Vidya-PRD.md` §5

---

## Acceptance criteria (from PRD)

- [ ] Sources: YouTube Data API v3, arXiv API, NPTEL (public), MIT OCW (public)
- [ ] Relevance ranking: semantic similarity to unit syllabus via text-embedding-004; top-N configurable (default 10)
- [ ] Faculty can add/remove items; additions marked "Faculty Recommended"
- [ ] Notebook Q&A: RAG over package content with source citations
- [ ] Web + mobile-responsive; offline PDF download
- [ ] Auto-update when syllabus version bumps; students notified
- [ ] Faculty notes (text/PDF) included and indexed for Q&A

---

## Architecture refinements (mandatory, incorporated 2026-05-15)

### R1 — Tenant-safe vector indexing

All Qdrant payloads, Celery task payloads, log context, and audit metadata carry explicit
tenant identifiers:

```json
{
  "tenant_schema": "tenant_xyz",
  "package_id": "...",
  "item_id": "...",
  "source_type": "YOUTUBE"
}
```

Celery task payloads always include `tenant_id` (UUID) and `tenant_schema` (str).
Qdrant retrieval always filters by `tenant_schema` + `package_id`.

### R2 — content_hash on package_items

`content_hash VARCHAR` on `package_items`.
SHA-256 of `normalize(url) + title + extracted_text_checksum`.
Dedup index: `(package_id, content_hash)`.
Used for: deduplication on ingest, syllabus-bump diffing, skip-if-unchanged indexing.

### R3 — Source adapter abstraction

```
m05_learning_materials/
  source_adapters/
    __init__.py
    base.py          AbstractSourceAdapter + RawItem dataclass
    youtube.py       YouTubeAdapter
    arxiv.py         ArxivAdapter
    nptel.py         NptelAdapter
    mit_ocw.py       MitOcwAdapter
```

Each adapter: `async def search(query: str, limit: int) -> list[RawItem]`.
`RawItem` carries: `source_type`, `title`, `url`, `raw_text`, `metadata`.

### R4 — Aggressive retry + timeout

Every adapter wraps httpx calls with:
- `httpx.AsyncClient(timeout=httpx.Timeout(10.0))`
- `tenacity` retry: 3 attempts, exponential backoff 1s→30s
- Raises `SourceAdapterError` on exhaustion
- Curation Celery task: catches `SourceAdapterError` per adapter, logs warning,
  continues with partial results. Package is READY even if 1–2 sources fail.

### R5 — Future-ready metadata JSONB

`package_items.metadata` reserved keys (Phase 2, do not implement now):
- `difficulty_level`
- `estimated_study_time`
- `learning_style_tags`

Current keys in use: `thumbnail_url`, `authors`, `duration_seconds`, `arxiv_id`,
`publish_date`, `abstract_snippet`.

### R6 — SaaS-safe structured logging

Every log call in M05 (service, workers, adapters, RAG) uses `extra=` with:
```python
{
  "tenant_schema": ...,
  "package_id":    ...,
  "celery_task_id": ...,    # from self.request.id in Celery tasks
  "source_provider": ...,   # adapter name
}
```
Consistent with `vidya.worker.*` logger pattern in existing modules.

### R7 — M03 immutability

M05 reads `syllabi` and `syllabus_units` (M02) directly via repository queries.
M05 does NOT import anything from `m03_course_kit`.
Syllabus-bump hook: M02 service calls `LearningPackageService.on_syllabus_version_bump()`
— one-directional, no M03 changes.

---

## Data model

### `learning_packages`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| syllabus_id | UUID FK→syllabi.id CASCADE | |
| unit_number | Integer | |
| version | Integer default 1 | syllabus version at curation time |
| status | String | PENDING/CURATING/READY/OUTDATED |
| top_n | Integer default 10 | configurable per institution |
| item_count | Integer default 0 | denormalized |
| qdrant_indexed | Boolean default false | |
| ai_model | String nullable | |
| prompt_hash | String nullable | |
| created_by_user_id | UUID | |
| curated_at | DateTime nullable | |
| created_at | DateTime | |
| updated_at | DateTime nullable | |

Indexes: (syllabus_id), (syllabus_id, unit_number), status, created_by_user_id

### `package_items`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| package_id | UUID FK→learning_packages.id CASCADE | |
| source_type | String | YOUTUBE/ARXIV/NPTEL/MIT_OCW/FACULTY_NOTE |
| title | String | |
| url | String nullable | null for some faculty notes |
| content_hash | String nullable | SHA-256 for dedup (R2) |
| metadata | JSONB default {} | see R5 for reserved keys |
| relevance_score | Float nullable | cosine vs unit syllabus embedding |
| faculty_recommended | Boolean default false | |
| added_by_user_id | UUID nullable | null = AI-curated |
| display_order | Integer default 0 | |
| qdrant_indexed | Boolean default false | |
| created_at | DateTime | |
| updated_at | DateTime nullable | |

Indexes: (package_id), source_type, (package_id, content_hash), (package_id, faculty_recommended)

### `package_qa_sessions`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| package_id | UUID FK→learning_packages.id CASCADE | |
| student_user_id | UUID | |
| created_at | DateTime | |
| updated_at | DateTime nullable | |

Indexes: (package_id), (package_id, student_user_id)

### `package_qa_messages`

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| session_id | UUID FK→package_qa_sessions.id CASCADE | |
| role | String | USER/ASSISTANT |
| content | Text | |
| sources | JSONB default [] | [{item_id, title, url, snippet, relevance_score}] |
| created_at | DateTime | |

Indexes: (session_id), (session_id, created_at)

---

## Steps

| # | Step | Files | Status |
|---|---|---|---|
| 01 | DB models | `m05_learning_materials/models.py` | [x] |
| 02 | Alembic migration | `alembic/tenant_versions/0008_tenant_create_m05_learning.py` | [x] |
| 03 | Pydantic schemas | `m05_learning_materials/schemas.py` | [x] |
| 04 | Source adapter base | `source_adapters/base.py` | [x] |
| 05 | Source adapter implementations | `source_adapters/{youtube,arxiv,nptel,mit_ocw}.py` | [x] |
| 06 | Embedder + ranker | `m05_learning_materials/embedder.py` | [x] |
| 07 | Repository | `m05_learning_materials/repository.py` | [x] |
| 08 | Curation Celery task | `workers/heavy/curate_learning_package.py` | [x] |
| 09 | Qdrant RAG indexer Celery task | `workers/heavy/index_package_rag.py` | [x] |
| 10 | RAG Q&A service | `m05_learning_materials/rag_service.py` | [x] |
| 11 | Package service layer | `m05_learning_materials/service.py` | [ ] |
| 12 | Router + RBAC | `m05_learning_materials/router.py` | [ ] |
| 13 | Config + wiring | `config.py`, `main.py`, `requirements.txt` | [ ] |
| 14 | Frontend student view + offline PDF | `frontend/src/pages/LearningPackage.tsx` | [ ] |
| 15 | Frontend Q&A chat | `frontend/src/components/NotebookQA.tsx` | [ ] |
| 16 | Frontend faculty curation | `frontend/src/pages/FacultyCurate.tsx` | [ ] |
| 17 | Smoke tests + end-to-end QA | `tests/m05/` | [ ] |

---

## New config keys

```
YOUTUBE_API_KEY=
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
M05_TOP_N_PER_UNIT=10
M05_EMBED_BATCH_SIZE=64
M05_RAG_TOP_K=5
M05_RAG_CHUNK_TOKENS=512
M05_RAG_CHUNK_OVERLAP=128
```

---

## New pip dependencies

```
qdrant-client>=1.9
google-generativeai>=0.7
tenacity>=8.2
httpx>=0.27
pymupdf>=1.24   # PDF text extraction for faculty notes
```
