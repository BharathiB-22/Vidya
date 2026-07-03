# Vidya — Course Kit & Learning Package Reality Audit

Truth-only audit of the current codebase (`C:\vidya`, branch `feature/erp-onboarding`, as of 2026-07-01). No design proposals. Every claim carries a `file:line` citation. Anything absent is marked **NOT IMPLEMENTED**.

---

## Phase 1 — Course Kit Reality

Scope: `backend/app/modules/m03_course_kit/{models,repository,router,schemas,service,ai_provider}.py`, `backend/app/workers/heavy/{course_kit_generation,course_kit_export}.py`, `frontend/src/{components,hooks,pages}/**courseKit**`, `backend/alembic/tenant_versions/0007_tenant_create_m03_course_kit.py`.

There is no `compliance.py` in m03 — compliance logic lives inline in `service.py`.

### 1. Complete lifecycle
**Y, partial approval semantics.** State machine `DRAFT → AI_GENERATING → PUBLISHED → ARCHIVED` (`models.py:14-18`). Create requires the parent syllabus to already be `DEAN_APPROVED`/`DEAN_LOCKED` (`service.py:218-237`). Publish (`service.py:332-381`), archive (`service.py:383-399`), fork-to-new-DRAFT for versioning (`service.py:401-490`). There is **no** two-party review state (no `PENDING_REVIEW`) — unlike the Syllabus module (M02), publish is a single-actor FACULTY/ADMIN action.

### 2. AI generation flow
**Y, production-grade, fully async.** `POST /{kit_id}/generate` (`router.py:267-315`, rate-limited 5/min), only from DRAFT (`service.py:170-177`). Writes a `task_jobs` row, flips status to `AI_GENERATING`, commits, then calls `generate_course_kit.delay(...)` (`service.py:179-198`) — never blocks the API thread. Stores `ai_model`, `prompt_hash` (`models.py:76-77`). Provider chain: Gemini → Groq → DeepSeek (`ai_provider.py:1548-1594`).

### 3. Slide generation pipeline
**Y, detailed, fixed structure.** Exactly 10 slide types enforced by prompt: TITLE, OBJECTIVES, CONCEPT, DEFINITION, WORKED_EXAMPLE, CODE, COMMON_MISTAKES, ACTIVITY, QUIZ, SUMMARY (`ai_provider.py:596-696`). Pydantic validation (`ai_provider.py:236-270`), answer-key leakage scan (`ai_provider.py:371-403`), soft/hard violation classification (`ai_provider.py:410-472, 548-568`), and a ~420-line Groq-output normalizer to repair schema drift (`ai_provider.py:933-1355`).

### 4. Export pipeline
**Y, real libraries, real files.** `python-pptx` renders per-slide-type content plus a teaching-plan table (`course_kit_export.py:281-973`). `reportlab` renders PDF/handout (`course_kit_export.py:1064-1068, 1299-1303`). Output uploaded to S3/MinIO via boto3, served via presigned URL (`service.py:612-631`). Export requires `PUBLISHED`/`ARCHIVED` status (`service.py:558-563`). `handout` format always strips speaker_notes/answer_key/model_answer/rubric; DEAN role gets sensitive-field omission on `pdf`/`pptx` too (`service.py:549-551`, `course_kit_export.py:8-11`).

### 5. Teaching Plan generation
**Y.** `teaching_plan` JSONB list (`models.py:73`, schema `schemas.py:63-70`), AI-generated with a code-level fallback synthesis from slides if the model omits it (`ai_provider.py:1292-1316`). Rendered as an actual PPTX table on export (`course_kit_export.py:903-922`). Frontend marks it explicitly read-only/AI-only (no faculty-authoring UI).

### 6. Lesson Plan generation
**Y, but thinner.** `lesson_plans` JSONB (`models.py:74`), schema `schemas.py:73-80`, AI-generated (`ai_provider.py:337-348`). **Not rendered in export** — no PPTX/PDF section for lesson plans was found; it exists in DB/API only.

### 7. Assignment generation
**Y, full CRUD + AI.** `KitAssignment` table (`models.py:142-172`): type enum CLASSWORK/HOMEWORK/CASE_STUDY, `model_answer`, `rubric` JSONB (≥3 criteria enforced by prompt, `ai_provider.py:685-686`), `current_events_toggle`. Full CRUD + audit logging (`router.py:749-829`). `model_answer` hidden from DEAN (`router.py:100-105`).

### 8. Compliance checks
**Y, but structural only — no NBA/NAAC logic.** `_build_compliance()` (`service.py:102-142`) checks minimum slide count, minimum quizlet count, non-empty teaching plan. `co_reference` fields exist on slides/quizlets/assignments but coverage is **never validated**. Enforced as a hard gate on publish (`service.py:354-361`).

### 9. Faculty editing capabilities
**Y, real, state-guarded.** PATCH/POST/DELETE on slides/quizlets/assignments, restricted to ADMIN/FACULTY (`router.py:66`), only while kit is DRAFT (`service.py:79-95`) — `AI_GENERATING` returns 409, `PUBLISHED`/`ARCHIVED` returns 409 ("fork to edit"). Slide reordering supported (`repository.py:435-451`). Real edit dialogs, not stubs (`SlideDialog.tsx` 338 lines, `AssignmentDialog.tsx` 219, `QuizletDialog.tsx` 182).

### 10. Approval workflow
**Partial — no dean/HOD sign-off gate on the kit itself.** DEAN role is read-only for course kits (`router.py:340-344`); no `approved_by`/`approved_at` column distinct from `published_by_user_id`/`published_at` (the publisher's own action). The only "approval" surfaces are: (a) the pre-condition that the syllabus must already be dean-approved, and (b) the compliance gate at publish time.

### 11. Version history
**Y.** `version` int + `parent_version_id` self-FK (`models.py:59-60`), one-published-per-unit invariant (`service.py:363-373`), `fork_kit` deep-copies everything into a new DRAFT at `version = max+1` (`service.py:401-490`). API `GET /{kit_id}/versions` (`router.py:248-260`); frontend `KitVersionHistory.tsx`.

### 12. Dean review workflow
**Partial.** No dedicated dean-review route — DEAN uses the same detail page, role-gated to read-only with sensitive fields nulled server- and client-side (`router.py:88-116`, `CourseKitDetailPage.tsx:49-63`). **No approve/reject action exists for dean on course kits** (contrast with the Syllabus module, which per recent commit history has a full reject/resubmit/dean-feedback workflow).

### 13. Faculty workflow
**Y, complete end-to-end.** Create → generate → edit → compliance-check → publish/archive/fork → export → download. `CreateCourseKitDialog.tsx`, `CourseKitActionBar.tsx`, section components for slides/quizlets/assignments/teaching plan, `ExportPanel.tsx`.

### 14. Student workflow
**NOT IMPLEMENTED.** No `STUDENT` role reference anywhere in `m03_course_kit` backend or frontend. No student route, no student-initiated export. The `handout` export exists only for FACULTY/ADMIN/DEAN requesters.

### Cross-cutting project-rule checks
- **Human ratification at DB level**: Partial — publish/archive are real DB-gated state transitions, but there's no second-party (dean) sign-off column for course kits specifically.
- **Async AI generation**: Confirmed — generation always runs via Celery (`course_kit_generation.py`), never on the request thread.
- **AuditLog fields (model, prompt_hash, output summary, confidence score)**: Partial. `model_used` and `prompt_hash[:16]` are logged, but into the generic `metadata` JSONB, not dedicated columns — the `AuditLog` model (`backend/app/core/audit_log/models.py:432-451`) has no `model`/`prompt_hash`/`confidence_score` columns at all. **No confidence score is computed anywhere in M03** — `KitGenerationResult` has no such field.

---

## Phase 2 — Learning Package Reality

Scope: `backend/app/modules/m05_learning_materials/`, `frontend/src/{components,hooks,pages}/**learningPackage**`, Qdrant/embeddings code across `backend/`.

This is **the most fully-built module in the audit scope** — backend, DB, Celery workers, and frontend are wired end-to-end, not stubs.

| Item | Status | Evidence |
|---|---|---|
| External resource collection | **Y** | `PackageItem` model, one table for all source types (`models.py:117-156`) |
| YouTube integration | **Y — real API** | YouTube Data API v3 search call (`source_adapters/youtube.py:16-45`) |
| Papers (distinct feature) | **NOT IMPLEMENTED** | No separate papers model; arXiv is the only paper source |
| Books | **NOT IMPLEMENTED** | No adapter/enum value anywhere in m05 |
| NPTEL | **Partial** | Best-effort scraping of Next.js `__NEXT_DATA__`; NPTEL has no public API; fails soft to `[]` (`source_adapters/nptel.py:1-10, 56-73`) |
| MIT OCW | **Partial** | Same scraping pattern (`source_adapters/mit_ocw.py:1-9, 55-73`) |
| arXiv | **Y — real API** | Public Atom API, no key needed (`source_adapters/arxiv.py:16-43`) |
| Faculty uploaded resources | **Y, three distinct paths** | See Phase 4 |
| Existing chatbot | **Y, real** | `POST /{package_id}/ask` (`router.py:389-412`), UI `NotebookQA.tsx` |
| Existing search | **NOT IMPLEMENTED (keyword)** | No DB-LIKE/full-text search exists; only outbound 3rd-party search + vector similarity |
| Existing RAG | **Y, real** | `rag_service.ask_package_question` (`rag_service.py:78-206`): embed → Qdrant filtered search → context build → Gemini/Groq generate |
| Existing embeddings | **Y, real** | `gemini-embedding-001`, 3072-dim (`embedder.py:42-117`, `index_package_rag.py:48`) |
| Existing vector search | **Y, real Qdrant queries** | `qdrant.query_points` filtered by `tenant_schema`+`package_id` (`rag_service.py:220-241`); collection `m05_rag` |

**Connection to Course Kit: NONE.** Grep in both directions found zero FK/import/shared-service link. `LearningPackage.syllabus_id` FKs to `syllabi.id` (M02), not to any Course Kit table (`models.py:74-79`). Comments in m05 note the code style mirrors m03's conventions — that is the only relationship (`embedder.py:15`, `service.py:4`).

Faculty-note upload path (the one true file-upload flow, detailed in Phase 4): validated content-type/size → text extraction (pypdf/python-docx) → best-effort S3 upload → dedup by content hash → feeds the RAG index. Router: `router.py:294-345`.

---

## Phase 3 — AI Reality

Two distinct code lineages exist:
- **Modern (m01, m02, m03)**: `google.genai` SDK + `AsyncOpenAI` for Groq/DeepSeek, JSON-schema-enforced structured output, Pydantic validation + salvage logic, Gemini → Groq → DeepSeek fallback chain.
- **Legacy (m06, m07, m08, m09)**: `google.generativeai` SDK, manual JSON regex extraction, Gemini → Groq only (**no DeepSeek**), template-based mock fallback on parse failure.

### Gemini
Model default `"gemini-2.0-flash"` (`config.py:71`). Modern lineage uses `response_schema` + `response_mime_type="application/json"` (true structured output). Legacy lineage has no schema enforcement — relies on prompt instructions + manual parsing. **No `max_output_tokens` set anywhere for Gemini**, in either lineage.

### Groq
Model `"llama-3.3-70b-versatile"` (`config.py:76`) everywhere. Modern lineage: OpenAI-compatible client, `response_format={"type":"json_object"}`, no `max_tokens` set. Legacy lineage: mixed SDK/raw-httpx calls, `max_tokens` capped (2048–4096 depending on file), no JSON-format enforcement.

### DeepSeek
Model `"deepseek-chat"` (`config.py:81`), **present only in m01, m02, m03** — legacy modules (m06-m09) have no DeepSeek path at all. Output reuses the same Groq normalizer functions (treated as equivalently "messy" as Groq's).

### Fallback order
Identical 3-provider chain shape in m01/m02/m03: `[("gemini", ...), ("groq", ...), ("deepseek", ...)]`, e.g. `m03/ai_provider.py:1548-1594`. Tries each in order, skips disabled/unconfigured providers, raises only if all fail. Legacy modules (m06-m09) hand-roll a Gemini→Groq-only fallback per file, no DeepSeek.

### Prompts, tokens, JSON, retry
- m03's system prompt is the most elaborate (~110 lines, `ai_provider.py:587-697`) — fixes exact slide order/structure and repeats the answer-key-leakage prohibition twice. Contains a **comment**, not an enforced parameter: `"Token budget target: ≤8,000 output tokens (safe for Groq free tier)"` (`ai_provider.py:583`).
- No retry-the-same-call logic anywhere in any `ai_provider.py` — "retry" means try the next provider. Celery-level `autoretry_for=(ConnectionError, TimeoutError, OSError)` exists but only covers infra errors, not AI parse/validation failures (`course_kit_generation.py:53-61`).
- All AI generation dispatches via Celery — confirmed non-blocking across every module with AI code.
- **AuditLog gap**: m02 and m03 log `model_used`/`prompt_hash` (in JSONB metadata, not dedicated columns). **m01 logs no AuditLog event for generation at all** — result only written to the `Program` row. **No module anywhere computes or logs a confidence score** — a direct deviation from the CLAUDE.md AuditLog rule.

### Which provider actually produces the highest-quality Course Kit slides?
Code-level evidence only, no speculation: Gemini is tried first unconditionally and is the only provider that gets true schema-enforced output (`response_schema`); Groq/DeepSeek output requires a ~420-line ad hoc normalizer to patch known shape deviations (`ai_provider.py:933-1355`). The size of that normalizer is itself code-level evidence that Groq/DeepSeek raw output diverges more from the target schema than Gemini's. The prompt text is identical across all three providers, and no token/context budget differs by provider. **This is evidence of a reliability/conformance advantage for Gemini, not a measured content-quality comparison** — no metric, score, or comment in the codebase ranks pedagogical/content quality between providers.

---

## Phase 4 — Faculty Resources

| Resource type | Status | Notes |
|---|---|---|
| PPT | **NOT IMPLEMENTED (upload)** | PPTX only exists as an AI-generated export artifact; faculty receive, never upload |
| PDF | **Partial** | Course-kit PDFs are generated exports, not uploads; genuine PDF *upload* exists only via m05 faculty notes |
| Notes | **Y — fullest implementation** | See walkthrough below |
| Videos | **NOT IMPLEMENTED** | Only `viva_recording` (m07, unrelated) and YouTube-by-URL (metadata only, no file) exist |
| External links | **Y, dominant mechanism in m05** | `PackageItem.url` is a bare string column — no file transfer at all |
| Labs | **NOT IMPLEMENTED** | No upload endpoint for faculty lab material; only student *submissions* use the generic storage flow |
| Reference books | **NOT IMPLEMENTED** | Only text/JSON bibliographic metadata exists (m02 `reference_clients.py`), no file, no storage entity type |
| General "learning resources" | **Partial** | Limited to `MaterialSourceType` enum (YOUTUBE/ARXIV/NPTEL/MIT_OCW/FACULTY_NOTE) — everything but FACULTY_NOTE is link/metadata only |

Storage abstraction (`backend/app/core/storage/`) is real: boto3 S3/MinIO client (`repository.py:32-41`), presigned-PUT flow, MIME whitelist (`config.py:131-168`), 50MB cap. `StorageEntityType` values are `submission, research_doc, course_kit, course_kit_export, viva_recording, program_export, syllabus_export, scanned_script, faculty_note` — note `course_kit` is a **defined but unused/dead** entity type; no router actually calls `/storage/upload-url` with it.

**Complete upload flow (faculty note, m05)** — the only genuine faculty file-upload path in the codebase:
1. UI: `NoteUploadForm` in `FacultyCurate.tsx:375-465`.
2. `POST /learning-packages/{package_id}/notes` (`router.py:294-345`), RBAC ADMIN/FACULTY, rate-limited 10/min.
3. `LearningPackageService.ingest_faculty_note` (`service.py:640-724+`): validates MIME (PDF/TXT/DOCX)/20MB cap, extracts text (pypdf/python-docx), uploads raw bytes to S3 **best-effort** (failure doesn't block item creation), dedupes by content hash, persists `PackageItem` FK'd to `learning_packages.id`.
4. Audit-logged (`LEARNING_PACKAGE_FACULTY_NOTE_UPLOADED`).
5. Downstream: extracted text feeds the RAG index; the raw S3 object is otherwise inert (no faculty-facing download endpoint found for notes).

---

## Phase 5 — Existing Chatbot

**One real chatbot exists, scoped to Learning Packages only.** No general-purpose assistant, no course-kit chatbot, no student-facing chatbot outside this module exists anywhere else in the codebase (confirmed by grep across both backend and frontend).

- Endpoint: `POST /{package_id}/ask` + session list/get (`m05/router.py:389-412`).
- Pipeline: embed question → Qdrant `query_points` filtered by `tenant_schema`+`package_id` → build numbered context from retrieved chunks → Gemini Flash generation with Groq fallback (`rag_service.py:78-454`).
- UI: `NotebookQA.tsx`, full chat bubble interface with session persistence, source citations, wired into `LearningPackage.tsx:847-866`.
- **What it can answer**: only questions groundable in the resources curated/uploaded into that specific learning package (arXiv/NPTEL/MIT OCW/YouTube metadata + faculty notes), retrieved via vector similarity — not general course content, not course-kit slide content (no connection, per Phase 2), not open-domain questions beyond what's indexed.

---

## Phase 6 — Electives

**Electives are a placeholder boolean, not a real feature.**

1. **Placeholder vs. real logic**: `is_elective` is a plain `Boolean` on `courses` (`m01_program_advisor/models.py:105`). The only real consumer is a compliance ratio check — `_check_elective_ratio()` warns if `elective_count / total < min_elective_ratio` per degree type (`compliance.py:228-245`). No other runtime logic branches on this flag.
2. **Elective groups as a DB entity**: **NOT IMPLEMENTED.** No `elective_group`/`elective_slot` table anywhere. Closest analog is `CoursePrerequisite` (`models.py:123-136`) — a different relationship (prerequisite chains), no slot/group semantics.
3. **Multiple subjects under one slot**: **NOT IMPLEMENTED.** No `elective_group_id` column exists on `courses` or elsewhere; two elective courses in the same semester are just two independent rows with nothing linking them as alternatives.
4. **Student selection**: **NOT IMPLEMENTED.** `AcadEnrollment` (`m_academics/models.py:139-152`) links `student_id → section_id` only — no `course_id` at all, so students can't be enrolled in a specific course, let alone choose between electives.
5. **Faculty assignment to a specific elective**: **NOT IMPLEMENTED.** `SubjectAssignment` (`m_academics/models.py:165-189`) has role enum `PRIMARY | CO_FACULTY | GUEST` — no elective-awareness; assigning to an elective course uses the identical path as a core course.
6. **Attendance/marks/timetable cross-references**: **NOT IMPLEMENTED, and no timetable module exists at all** — zero `elective`/`is_elective` references found in `m11_sis` attendance/marks/exam models (0 grep hits), and no `**/*timetable*` or `**/*schedul*` files exist under `backend/app/modules/`.

---

## Phase 7 — Improvement Compatibility

Assessed against the architecture actually found in Phases 1-6. No implementation proposed.

| # | Idea | Foundation | Basis |
|---|---|---|---|
| 1 | 10-15 professional AI slides | **Partial** | Full schema/validation/PPTX-renderer machinery exists per slide type, but slide count and order are hardcoded to a fixed 10-type sequence in the prompt and renderer registry (Phase 1 §3) — extending count touches prompt, schema enum, and renderer, not a config value |
| 2 | Faculty-uploaded resources alongside AI content | **Partial** | Zero upload capability exists inside m03 itself (Phase 4) — but a working, provable pattern (storage abstraction + note ingestion + text extraction) already exists in the sibling module m05 and could be replicated; it is not present in Course Kit today |
| 3 | Learning Package as richer student hub | **Existing foundation** | RAG chatbot, resource curation, embeddings, vector search, and a student-facing UI already work end-to-end (Phase 2) — this is the strongest existing base of any item in this list |
| 4 | Student AI tutor per course | **Partial** | The RAG/chat pattern exists and works, but it is scoped to a Learning Package (tied to a syllabus via `syllabus_id`), not to a course directly, and has zero connection to Course Kit content (Phase 2) |
| 5 | Elective Groups (multi-subject slots) | **No foundation** | Confirmed placeholder-only; would require new tables/FKs with no existing analog beyond an unrelated prerequisite join table (Phase 6) |
| 6 | Dean rejection/resubmission for Course Kits | **Partial** | No such status or action exists in m03 (Phase 1 §10, §12) — but an equivalent full reject/resubmit/dean-feedback workflow already exists and works in the sibling Syllabus module (M02, per `SyllabusListPage.tsx:153-157` handling `REJECTED`/`dean_comment`/`[REVISION REQUESTED]`), so a proven in-repo pattern exists, just not wired to Course Kit |
| 7 | Course Kit cards matching Syllabus UI | **Partial** | Verified directly: both list pages share the same visual shell (`rounded-xl border divide-y bg-white`, `*StatusBadge` component), but `SyllabusListPage.tsx:170-186` resolves and shows `course_title`/`program_name`/`semester`/`course_code`, while `CourseKitListPage.tsx:171-185` shows only `Unit N — vN` + a raw `syllabus_id` UUID when not scoped to a syllabus — the name-resolution work done for Syllabus (commit `a6e14047`) was never applied to Course Kit |

---

## Final Deliverable

**1. What already exists (production-grade, real):**
- Course Kit CRUD, state machine, AI generation (async, 3-provider fallback), compliance gate, versioning/fork, PPTX/PDF export with role-based content sanitization, faculty edit workflow. (Phase 1)
- Learning Package resource curation (arXiv, YouTube — real APIs; NPTEL/MIT OCW — best-effort scraping), faculty note upload with text extraction, full RAG pipeline (embeddings → Qdrant → Gemini/Groq generation), student-facing chat UI. (Phase 2, 5)
- AI provider fallback chain (Gemini → Groq → DeepSeek) with structured-output enforcement for Gemini and schema-repair normalization for Groq/DeepSeek, in the modern module lineage (m01/m02/m03). (Phase 3)
- Generic S3/MinIO storage abstraction with presigned URLs and MIME/size validation. (Phase 4)

**2. What is partially implemented:**
- Course Kit approval — publish exists, dean sign-off/reject-resubmit does not (pattern exists in Syllabus module, not ported).
- Lesson plans — generated and stored, never rendered into export output.
- Compliance checks — structural completeness only, no CO-coverage or NBA/NAAC-specific validation despite `co_reference` fields existing.
- AuditLog for AI — model/prompt_hash logged in free-form metadata; no confidence score anywhere; m01 logs no AuditLog event for generation at all. This is a direct gap against the CLAUDE.md non-negotiable rule.
- Faculty resource upload — real and complete for notes (PDF/TXT/DOCX) in m05; everything else (PPT, video, labs, books) is either a generated export, a link/metadata field, or absent.
- NPTEL/MIT OCW integration — functional but explicitly best-effort scraping with no stable API, silently degrades to empty results.

**3. What is completely missing:**
- Any connection between Course Kit and Learning Package (separate data models, separate everything).
- Student-facing surface for Course Kit (no role, no route, no export path).
- Elective groups, student elective selection, elective-aware faculty assignment, and any timetable module at all.
- File upload for PPT, video, lab manuals, or reference books anywhere in the platform.
- In-app keyword/full-text search over resources or courses (only vector search and outbound third-party API search exist).
- Confidence scoring for any AI-generated content.

**4. What should NOT be rebuilt (already works):**
- The Course Kit AI generation, validation, and export pipeline (Phase 1 §2-4, §7) — this is deep, tested-shaped logic (safety scanning, salvage/repair, per-slide-type rendering) and reworking it risks regressing a working system.
- The Learning Package RAG stack (Phase 2, 5) — embeddings, Qdrant indexing, and the chat UI are a complete, working loop; any "student tutor" or "richer hub" work should extend this, not replace it.
- The AI provider fallback chain shape in m01/m02/m03 (Phase 3) — the chain-of-providers pattern with per-provider normalization is consistent and functional; the legacy m06-m09 lineage is the outlier that lacks this robustness, not the modern lineage.
- The generic storage abstraction (Phase 4) — presigned-URL upload flow is sound and reusable as-is for any new upload type.

**5. What can be enhanced safely without breaking architecture:**
- Wiring m05's proven upload pattern into m03 for faculty-supplied slides/PDFs (additive — new endpoint/entity type, no change to existing generation/export code).
- Porting the Syllabus module's dean reject/resubmit pattern to Course Kit (additive — new status value + router action, existing state machine already has room for it).
- Resolving `course_title`/`program_name` on the Course Kit list view the same way Syllabus already does (frontend-only, no backend/schema change — the data is already fetchable, just not joined/displayed).
- Adding a confidence score field to `AuditLog` and to AI generation result schemas (additive column/field, does not touch existing generation logic).
