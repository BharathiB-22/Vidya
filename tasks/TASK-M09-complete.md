# TASK-M09 — M09 Paper Administration & Scanning: COMPLETE

**Phase:** 2 — Assess and Research
**Module path:** `backend/app/modules/m09_paper_admin/`
**Stack:** Python 3.12, FastAPI, Celery, React 18, TypeScript, PostgreSQL 16, Gemini 2.0 Flash, Groq llama-3.3-70b
**Status:** CLOSED — all steps implemented, tested, and validated
**Closed:** 2026-05-18

---

## Module Purpose

M09 Paper Administration manages the full lifecycle of scanned physical answer scripts:
upload → AI scoring (Celery) → evaluator marks entry (Gate 1) → Board finalisation (Gate 2) → append-only score ledger.

Key design principle: **AI advises, humans decide.** The AI scorer (Gemini → Groq fallback) provides
suggested marks per question. A human evaluator must enter final marks. A Board member must
explicitly finalise before any score is recorded. No autonomous grade writing at any stage.

Student identity is masked from all evaluators via a random `masked_id` token (e.g. `S3F9A2C14B`)
until Board Gate 2 completes — at which point identity is revealed only to authorised Board/Admin roles.

---

## Completed Commits

| Commit | Steps | Scope |
|--------|-------|-------|
| `0edf2dd` | STEP-01..04 | Models, Alembic migration, Pydantic schemas, repository layer |
| `f7fba13` | STEP-05 | `script_scorer.py` + `score_scanned_script` Celery worker + M09 audit event types |
| `4bee1bc` | STEP-06 | Service layer — evaluator and Board human-gate invariants |
| `5a9a672` | STEP-07..08 | HTTP router (13 endpoints, RBAC) + `main.py` `/scripts` registration |
| `cdb59c4` | STEP-10 | Frontend TypeScript types (`script.ts`) + API client (`scripts.ts`) |
| `d5a651c` | STEP-11..15 | Frontend pages (ScriptListPage, ScriptUploadPage, ScriptEvaluationPanel, BoardScriptReviewPage) + App.tsx routes |
| `9cd1d30` | STEP-16..17 | Backend test suite (112 tests, 0 fail) + `celery_app.conf.include` fix + completion report |

---

## Backend Files

### Created

| File | Purpose |
|------|---------|
| `backend/app/modules/m09_paper_admin/__init__.py` | Package marker |
| `backend/app/modules/m09_paper_admin/models.py` | SQLAlchemy models: `ScannedScript`, `ScriptEvaluation`, `ExamScoreLedger`; `ScriptStatus` and `EvaluationRound` enums |
| `backend/app/modules/m09_paper_admin/schemas.py` | Pydantic v2 request/response schemas; `BulkMarkUpdate` and `ScriptSubmitMarksRequest` validators |
| `backend/app/modules/m09_paper_admin/repository.py` | `ScriptRepository`, `ScriptEvaluationRepository`, `ExamScoreLedgerRepository`, `TaskJobPublicRepository` |
| `backend/app/modules/m09_paper_admin/script_scorer.py` | Per-question AI scoring: MCQ regex heuristics + Gemini → Groq fallback for subjective questions; `QuestionScore` and `ScriptScoringResult` dataclasses |
| `backend/app/modules/m09_paper_admin/service.py` | `ScriptService` with `ingest_script`, `assign_evaluator`, `update_evaluator_marks`, `submit_marks` (Gate 1), `board_finalise` (Gate 2), list/get/ledger methods |
| `backend/app/modules/m09_paper_admin/router.py` | FastAPI `APIRouter` — 13 endpoints; static paths before `/{script_id}` param to prevent routing conflicts |
| `backend/app/workers/heavy/score_scanned_script.py` | Celery heavy-queue task; singleton async engine; `max_retries=2`; never writes `evaluator_marks` or `exam_score_ledger` |
| `backend/tests/modules/m09_paper_admin/__init__.py` | Test package marker |
| `backend/tests/modules/m09_paper_admin/test_unit.py` | 112-test unit suite (9 test classes) |

### Modified

| File | Change |
|------|--------|
| `backend/app/core/audit_log/models.py` | Added 8 M09 `AuditEventType` values |
| `backend/app/main.py` | Registered `/scripts` router |
| `backend/app/workers/celery_app.py` | Added `score_scanned_script` to `conf.include` |
| `backend/alembic/versions/0014_m09_paper_admin.py` | Tenant-schema migration for `scanned_scripts`, `script_evaluations`, `exam_score_ledger` |

---

## Frontend Files

### Created

| File | Purpose |
|------|---------|
| `frontend/src/types/script.ts` | TypeScript union types and interfaces for M09 API |
| `frontend/src/lib/api/scripts.ts` | 15 typed API functions (`uploadScript`, `assignEvaluator`, `updateMarks`, `submitMarks`, `boardFinalise`, `getScript`, `listAllScripts`, `listBoardPending`, `listMyScripts`, `listScriptsForPaper`, `getEvaluations`, `getLedgerEntry`, `listLedgerForPaper`, `getScoringJobStatus`) |
| `frontend/src/pages/ScriptListPage.tsx` | Admin/Board: paginated list of all scripts with status filter chips and action buttons |
| `frontend/src/pages/ScriptUploadPage.tsx` | Admin: script ingest form — exam paper ID, S3 object key, optional student identity with privacy warning |
| `frontend/src/pages/ScriptEvaluationPanel.tsx` | Evaluator: per-question marks entry panel with AI suggestion display, save (no gate), Gate 1 submit with completeness validation |
| `frontend/src/pages/BoardScriptReviewPage.tsx` | Board: Gate 2 review — expandable script cards, evaluation summary, two-step confirm before finalise |

### Modified

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Added 4 M09 routes: `/scripts`, `/scripts/upload`, `/scripts/board`, `/scripts/:scriptId/evaluate` |

---

## API Endpoints

All endpoints mount under `/scripts`.

| Method | Path | Role | Purpose |
|--------|------|------|---------|
| POST | `/scripts/upload` | ADMIN, BOARD | Ingest scanned script + queue AI scoring |
| GET | `/scripts` | ADMIN, BOARD | List all scripts with status/paper filters |
| GET | `/scripts/board/pending` | BOARD, ADMIN | Scripts awaiting Board finalisation |
| GET | `/scripts/evaluator/me` | FACULTY, ADMIN | Evaluator's own assigned scripts |
| GET | `/scripts/paper/{paper_id}` | ADMIN, BOARD | Scripts for an exam paper |
| GET | `/scripts/{script_id}` | All roles | Script detail (identity masked pre-finalise) |
| POST | `/scripts/{script_id}/assign` | ADMIN, BOARD | Assign evaluator(s) |
| PATCH | `/scripts/{script_id}/marks` | FACULTY, ADMIN | Save evaluator marks (intermediate, no gate) |
| POST | `/scripts/{script_id}/submit` | FACULTY, ADMIN | **Gate 1**: evaluator submits all marks |
| POST | `/scripts/{script_id}/finalise` | BOARD, ADMIN | **Gate 2**: Board finalises + writes ledger |
| GET | `/scripts/{script_id}/evaluations` | All roles | AI suggestions + evaluator marks per question |
| GET | `/scripts/{script_id}/ledger` | BOARD, ADMIN | Board-finalised score record |
| GET | `/scripts/ledger/paper/{paper_id}` | BOARD, ADMIN | Ledger entries for an exam paper |

---

## Human-Gate Invariants

These invariants are enforced at the service layer and tested in the unit suite:

| Invariant | Enforcement |
|-----------|-------------|
| `evaluator_marks` is **never** written by any Celery task | `score_scanned_script` only writes `ai_suggested_marks` via `bulk_create_ai_suggestions()` |
| `exam_score_ledger` is written **only** by `board_finalise()` | `ExamScoreLedgerRepository.create()` is called exclusively inside `ScriptService.board_finalise()` |
| Celery task **never** advances status beyond `SCORED` | Task sets `SCORED` or `REVIEW_REQUIRED` only; `MARKS_SUBMITTED` and `BOARD_FINALISED` are human-only transitions |
| Gate 1 requires **all** evaluations to have marks | `submit_marks()` checks for `None` evaluator_marks before transitioning |
| Gate 2 requires status `MARKS_SUBMITTED` | `board_finalise()` raises `INVALID_STATUS` 400 for any other status |
| Only the assigned evaluator can submit at Gate 1 | `submit_marks()` checks `evaluator_user_id in {evaluator_id, second_evaluator_id}` |
| `exam_score_ledger` has **no** update or delete repository methods | `ExamScoreLedgerRepository` exposes only `create`, `get_by_script`, `list_for_exam_paper` |
| Re-assigning evaluator is blocked after `BOARD_FINALISED` | `assign_evaluator()` raises `INVALID_STATUS` if script is finalised |

---

## Security, RBAC, and Tenant Isolation

- **Multi-tenant isolation:** All three M09 tables (`scanned_scripts`, `script_evaluations`, `exam_score_ledger`) live in the tenant schema. Every query scopes to the tenant via SQLAlchemy's async session bound to the correct schema.
- **Identity masking:** `student_user_id` and `student_roll_ref` are set to `None` in-memory (never persisted as `None`) on every API response path until `status == BOARD_FINALISED`. The service layer's `_mask_identity()` function handles this uniformly; the router never strips identity itself.
- **RBAC groups:**
  - `_INGEST` — ADMIN, BOARD (upload, assign evaluator)
  - `_EVALUATE` — FACULTY, ADMIN (enter/save marks, Gate 1 submit)
  - `_BOARD` — BOARD, ADMIN (Gate 2 finalise, ledger read)
  - `_READ` — all tenant roles (script detail, evaluations, list)
- **Audit log:** Every state-changing action appends an immutable `AuditLog` row. The 8 M09 event types cover: scoring queued, scoring completed, scoring failed, evaluator assigned, marks updated, marks submitted (Gate 1), board finalised (Gate 2), score recorded.
- **Audit log is append-only:** No `UPDATE` or `DELETE` on `audit_logs` — enforced by project policy and tested in M03 audit suite.
- **AI output logged:** Gemini/Groq model name, prompt hash, and justification are stored per `ScriptEvaluation` row.

---

## Audit Event Types (8 added to `AuditEventType`)

```
SCRIPT_SCORING_QUEUED      — Celery task dispatched
SCRIPT_SCORING_COMPLETED   — AI scoring finished
SCRIPT_SCORING_FAILED      — Celery task failed
SCRIPT_EVALUATOR_ASSIGNED  — Evaluator assigned by Admin
SCRIPT_MARKS_UPDATED       — Evaluator saved marks (intermediate)
SCRIPT_MARKS_SUBMITTED     — Gate 1: evaluator submitted all marks
SCRIPT_BOARD_FINALISED     — Gate 2: Board finalised script
EXAM_SCORE_RECORDED        — Ledger entry written
```

---

## Validation Results

| Check | Result |
|-------|--------|
| M09 unit tests | **112 / 112 passing** |
| M06 + M07 + M08 + M09 regression | **298 / 298 passing** |
| Frontend TypeScript (`npx tsc --noEmit`) | **Clean — 0 errors** |
| `score_scanned_script` in `celery_app.conf.include` | Fixed in STEP-16 commit |

---

## Known Limitations and Future Work

| Item | Status |
|------|--------|
| **OCR pipeline** | Placeholder only. `ocr_text` field is reserved; no OCR extraction implemented this sprint. Scripts uploaded without OCR text receive status `REVIEW_REQUIRED` and all `ai_suggested_marks = None`. |
| **Scanner/S3 integration** | The upload endpoint accepts an S3 object key (`upload_url`) as a string. Actual PDF upload to MinIO/S3 and OCR extraction (e.g. Tesseract, AWS Textract) are out of scope for M09. |
| **Subjective AI suggestions require human review** | LLM marks for SHORT_ANSWER, LONG_ANSWER, and PROBLEM_SOLVING questions are advisory only. The UI and audit trail make this clear. No autonomous grade writing. |
| **Multi-round moderation** | `EvaluationRound` enum supports SECONDARY and MODERATION values. The service and router handle only PRIMARY this sprint. Secondary evaluator assignment is accepted as a field but not acted on separately. |
| **Concurrent edit locking** | `locked_by` / `locked_at` columns are present in the model as schema placeholders. No locking logic is implemented. |
| **MCQ answer extraction** | Regex heuristics work for well-formatted OCR output. Poor scan quality or non-standard answer formats will yield `ai_suggested_marks = None` — evaluator must enter manually. |
| **Score ledger queries** | Ledger listing for a paper is available. Ranking, percentile, and bell-curve analysis are deferred to M10. |

---

## Final Status

**M09 Paper Administration & Scanning is COMPLETE.**

All backend layers (models → migration → repository → Celery scorer → service → router) and all frontend layers (TypeScript types → API client → 4 pages → App.tsx routes) are implemented, tested, and regression-verified.

The module is ready for integration testing once a live PostgreSQL tenant schema is provisioned and a Celery worker is started. The next module in Phase 2 is **M10 Bell Curve Analysis**.
