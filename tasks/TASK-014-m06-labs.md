# TASK-014 — M06 Labs & Assignment Evaluator

**Phase:** 2 — Assess and Research
**Module path:** `backend/app/modules/m06_labs_evaluator/`
**Stack:** Python 3.12, FastAPI, Celery, React 18, TypeScript, PostgreSQL 16, Gemini 2.0 Flash, Groq llama-3.3-70b

---

## PRD Reference

F-06: Labs & Assignment Evaluator — `Vidya-PRD.md` §7

---

## Acceptance criteria (from PRD)

- [x] Faculty can create assignments (WRITTEN or CODE) with rubric and test cases
- [x] Faculty can publish, close, and archive assignments
- [x] Students submit text or code; system queues AI evaluation automatically
- [x] AI content scan flags possible AI-generated submissions (configurable threshold)
- [x] Plagiarism detection across cohort submissions
- [x] LLM-based per-criterion rubric scoring with justifications (Gemini → Groq fallback)
- [x] Code submissions run against test cases in sandboxed environment
- [x] Static analysis (complexity + issues) reported for code submissions
- [x] Faculty review panel: view submission, see AI scores, override per criterion
- [x] Human ratification is mandatory; grade ledger is written ONLY via the ratify endpoint
- [x] Moderation report (CSV) downloadable per assignment
- [x] Student result view shows final grade only after ratification
- [x] Multi-tenant isolation enforced throughout
- [x] Audit log on every state-changing action

---

## Implementation plan — 17 steps

| Step | Scope | Commit |
|------|-------|--------|
| 01 | Models + Alembic migration (0009ten) | `0836f65` |
| 02 | Assignment CRUD — repository, schemas, service, router | `7d3423d` |
| 03–08 | Evaluation pipeline: AI scan, plagiarism, rubric scorer, code sandbox, static analyser, AST similarity, Celery task | `788ddf7` |
| 09–11 | Faculty review API, grade ledger + ratify endpoint, CSV report export | `788ddf7` |
| 12–15 | Frontend: 6 pages + App.tsx routes | `a416dea` |
| 16–17 | 70 unit + wiring tests; TypeScript typecheck clean | `71b5f08` |

---

## Architecture completed

### Database (tenant-schema tables)

| Table | Purpose |
|-------|---------|
| `lab_assignments` | Assignment definitions; status DRAFT→PUBLISHED→CLOSED→ARCHIVED |
| `lab_submissions` | Student submissions; status SUBMITTED→EVALUATING→EVALUATED→REVIEWED→RATIFIED |
| `lab_evaluations` | AI evaluation output (rubric scores, test results, plagiarism, static analysis); 1:1 with submission |
| `grade_ledger` | Append-only final grades; UNIQUE on `submission_id`; FK with `ondelete=RESTRICT` |

### Backend scope (`backend/app/modules/m06_labs_evaluator/`)

| File | Role |
|------|------|
| `models.py` | SQLAlchemy models for all 4 tables |
| `repository.py` | Static-method repositories (AssignmentRepository, SubmissionRepository, EvaluationRepository, GradeLedgerRepository) |
| `schemas.py` | Pydantic request/response models with field validators |
| `service.py` | Business logic: AssignmentService, SubmissionService, ReviewService; LabServiceError |
| `router.py` | 15 endpoints mounted at `/labs` |
| `ai_scan.py` | Heuristic AI content detection (burstiness + repetition + vocab richness) — zero external deps |
| `plagiarism.py` | Character n-gram TF-IDF cosine similarity — zero external deps |
| `rubric_scorer.py` | LLM rubric scoring via Gemini → Groq fallback; `score_submission()` |
| `code_sandbox.py` | `subprocess.run()` sandbox; `sys.executable`; supports python/python3 |
| `static_analyser.py` | McCabe complexity (radon) + unused imports (pyflakes); graceful degradation |
| `ast_similarity.py` | AST normalisation + cosine similarity; detects variable-rename plagiarism |
| `report_export.py` | CSV moderation report generator |

**Celery task:** `backend/app/workers/heavy/evaluate_lab_submission.py`
Registered as `"app.workers.heavy.evaluate_lab_submission"` in `celery_app.py`.

### Frontend scope (`frontend/src/`)

| File | Role |
|------|------|
| `types/labs.ts` | TypeScript interfaces for all M06 entities |
| `lib/api/labs.ts` | API client functions (all `/labs/*` endpoints) |
| `hooks/labs/useLabs.ts` | React Query hooks (faculty + student) |
| `hooks/labs/useLabMutations.ts` | Mutation hooks (create, publish, close, submit, scores, ratify) |
| `components/labs/LabStatusBadge.tsx` | DRAFT/PUBLISHED/CLOSED/ARCHIVED badge |
| `components/labs/AIScanBadge.tsx` | PENDING/CLEAN/FLAGGED badge with probability |
| `components/labs/ConfidenceBadge.tsx` | HIGH/MEDIUM/LOW confidence badge |
| `pages/LabAssignmentListPage.tsx` | Faculty: assignment list with status filter + create dialog |
| `pages/LabAssignmentDetailPage.tsx` | Faculty: tabbed detail (overview + submissions) |
| `pages/LabReviewPanel.tsx` | Faculty: split-view review + per-criterion edit + two-step ratify |
| `pages/StudentLabListPage.tsx` | Student: assignment list with submission status |
| `pages/StudentSubmitPage.tsx` | Student: submit form (text/code) with deadline warning |
| `pages/StudentResultPage.tsx` | Student: ratified grade card + per-criterion breakdown |

---

## Test counts

| Suite | Tests | Result |
|-------|-------|--------|
| M06 unit tests (`test_unit.py`) | 51 | 51/51 PASS |
| M06 wiring tests (`test_wiring.py`) | 19 | 19/19 PASS |
| **M06 total** | **70** | **70/70 PASS** |
| M05 regression check (post-M06) | 166 | 166/166 PASS |

---

## Key commits (on `master`)

| Commit | Description |
|--------|-------------|
| `0836f65` | STEP-01: models + migration 0009ten |
| `7d3423d` | STEP-02: AssignmentService, CRUD router, schemas, repository |
| `788ddf7` | STEP-03..11: evaluation pipeline (AI scan, plagiarism, rubric scorer, code sandbox, static analyser, AST similarity, Celery task, review API, ratify endpoint, CSV report) |
| `a416dea` | STEP-12..15: 15 frontend files (types, API, hooks, components, pages, routes) |
| `71b5f08` | STEP-16..17: 70 tests, Celery include fix, TS typecheck clean |

---

## Manual QA status

**Not performed in this session.** Unit + wiring tests validate all module boundaries.
A live manual QA cycle requires:
- Running backend (`uvicorn app.main:app`) against a real PostgreSQL + Redis instance
- Running frontend dev server (`npm run dev`)
- Celery worker (`celery -A app.workers.celery_app worker --pool=solo -Q celery-heavy`)
- Full faculty workflow: create assignment → publish → student submits → wait for evaluation → review scores → ratify
- Full student workflow: list assignments → submit → view result after ratification

These require live Gemini API key and are deferred to the integration QA sprint.

---

## Known limitations

| ID | Limitation | Severity | Notes |
|----|------------|----------|-------|
| L1 | Code sandbox is `subprocess.run()` only; no Docker isolation | Medium | Acceptable for dev; swap `SandboxRunner` for Docker in prod |
| L2 | AI scan uses lightweight heuristics; no ML model | Medium | Replacement with fine-tuned RoBERTa is plug-compatible at `scan()` call site |
| L3 | Plagiarism works in-memory up to ~500 submissions | Low | For larger cohorts, replace with Qdrant embedding search |
| L4 | Code sandbox supports only Python; JS/Java not implemented | Low | Single `if language not in (...)` guard; extend `SandboxRunner` per language |
| L5 | File-upload submissions (content_url path) not exercised in tests | Low | URL path exists in models and service; tested indirectly via type coverage |
| L6 | Student result page fetches via `ReviewPanel` type; typing is cast not validated | Low | Backend enforces RATIFIED guard; frontend cast is safe but not strict |
| L7 | No real-time notifications to student when grade is ratified | Low | Notification module (M-notifications) is out of M06 scope |

---

## Production-readiness status

| Area | Status | Notes |
|------|--------|-------|
| Tenant isolation | READY | `schema_name` flows through all Celery kwargs; every query scoped |
| RBAC | READY | `require_roles` guards on all faculty endpoints |
| Human-gate invariant | READY | DB-level UNIQUE + RESTRICT; service-level single call site |
| Audit logging | READY | 13 AuditEventType values; all state transitions logged |
| Celery task | READY | Retry with backoff; job lifecycle tracked in `task_jobs` |
| Code sandbox | NOT PROD-READY | Needs Docker isolation before production deployment |
| AI scan | NOT PROD-READY | Heuristics only; acceptable for dev/demo |
| Secret management | READY | All keys from `settings` (env vars); no hardcoded secrets |
| TypeScript | READY | 0 type errors |
| Tests | READY | 70/70 pass; 166/166 M05 regression pass |

**Overall:** Development-complete and demo-ready. Code sandbox and AI scan require hardening before production.

---

## Final QA sign-off

- [x] All 17 implementation steps complete
- [x] 70/70 automated tests passing
- [x] TypeScript typecheck: 0 errors
- [x] M05 regression: 166/166 passing (no regressions)
- [x] Human-gate invariant verified at DB and service layer (wiring tests)
- [x] Grade ledger FK + UNIQUE constraints confirmed by test
- [x] Celery task registered in `celery_app.conf.include`
- [ ] Live end-to-end manual QA — deferred to integration sprint
- [ ] Docker sandbox hardening — deferred to production sprint
- [ ] Load test for plagiarism at 500+ submission cohort — deferred
