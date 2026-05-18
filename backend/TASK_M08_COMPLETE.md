# TASK-M08 Exam Setter — COMPLETE

**Closed:** 2026-05-18
**Branch:** master
**Final commit:** (to be tagged after STEP-17..18 commit)

## Module: M08 Exam Setter

Phase 2 module for AI-assisted exam paper generation, board review, sealing,
and timed release. All human-gate invariants enforced at both service and DB level.

---

## Step Completion Summary

| Step | Description | Status |
|------|-------------|--------|
| 01 | Models + Alembic migration (0011ten) | COMPLETE |
| 02 | Repository layer | COMPLETE |
| 03 | Schemas + Pydantic validators | COMPLETE |
| 04 | BloomsAnalyser + PaperSealer + QuestionGenerator | COMPLETE |
| 05 | Config additions (EXAM_FERNET_KEY, M08_* settings) | COMPLETE |
| 06 | Audit event types (12 new M08 events) | COMPLETE |
| 07 | Service layer (ExamService, 3 human gates) | COMPLETE |
| 08..09 | HTTP router (15 endpoints, 3 human gates) | COMPLETE |
| 10 | Celery tasks (generate_exam_paper, release_exam_paper) + celery_app include + main.py | COMPLETE |
| 11..16 | Frontend pages (List/Create/Editor/BoardReview) + API client + types + App.tsx routes; TS clean | COMPLETE |
| 17 | Test suite: 75 tests, 0 failures | COMPLETE |
| 18 | Celery smoke test + task completion file | COMPLETE |

---

## Test Results

- M08 tests:  75/75 PASS
- M07 tests:  41/41 PASS (no regression)
- M06 tests:  70/70 PASS (no regression)
- Total:     186/186 PASS

---

## Architecture

### Human Gates (DB-level, not UI-only)

1. **Gate 1** — `ExamService.submit_for_review()`: creator-only, GENERATED/BOARD_RETURNED→SUBMITTED
2. **Gate 2** — `ExamService.board_decide()`: board/admin, SUBMITTED→BOARD_APPROVED/BOARD_RETURNED
3. **Gate 3** — `ExamService.seal()`: creator-only, BOARD_APPROVED→SEALED; Fernet encrypt + S3 store + ETA Celery release

### Security invariants

- Sealed paper: questions return 403 (SEALED_ACCESS) until RELEASED
- Model answers: stripped in service layer when `include_answers=False`; never in base response schema
- Crypto key: `EXAM_FERNET_KEY` env var only; `encryption_key_ref` (string "EXAM_FERNET_KEY") stored in DB — never the actual key
- Answers export: FACULTY/BOARD/ADMIN only; student role blocked at router

### Key files

```
backend/app/modules/m08_exam_setter/
├── models.py              ExamPaper, ExamQuestion, BloomsComplianceReport, 4 enums
├── repository.py          ExamPaperRepository, ExamQuestionRepository, BloomsRepository
├── schemas.py             Pydantic v2 schemas + validators (BloomsDistribution, BoardDecision, SealRequest)
├── blooms_analyser.py     Pure functions: compute_actual_distribution, check_compliance
├── question_generator.py  Gemini→Groq→mock LLM pipeline
├── paper_sealer.py        Fernet AES seal/unseal; key_ref=env var name only
├── service.py             ExamService (all business logic, 3 human gates)
└── router.py              15 endpoints (FACULTY/BOARD/READ RBAC)

backend/app/workers/heavy/
├── generate_exam_paper.py  Celery: DRAFT→GENERATED, M02 syllabus integration
└── release_exam_paper.py   Celery: SEALED→RELEASED (ETA-scheduled)

backend/alembic/tenant_versions/
└── 0011_tenant_create_m08_exam.py

frontend/src/
├── types/exam.ts
├── lib/api/exam.ts
└── pages/
    ├── ExamPaperListPage.tsx
    ├── ExamPaperCreatePage.tsx
    ├── ExamPaperEditorPage.tsx
    └── BoardReviewPage.tsx
```

---

## Known non-blocking items

- PDF export is JSON-based (PDF generation marked as future enhancement in router comment)
- EXAM_FERNET_KEY blank in dev → ephemeral key with logged warning (expected behaviour)
- M02 syllabus fallback to stub units when no locked syllabus exists (dev/test safe)
