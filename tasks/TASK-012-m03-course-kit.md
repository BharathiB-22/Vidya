# TASK-012 — M03 Course Kit Builder

Phase 1, Module 3. Generates complete per-unit teaching kits from approved syllabi.

## Stack

Python 3.12 · FastAPI · Celery (heavy queue) · SQLAlchemy async · PostgreSQL 16
React 18 · TypeScript · shadcn/ui · python-pptx · ReportLab · Gemini / Groq / Fallback AI

## Module Path

`backend/app/modules/m03_course_kit/`

## Approved Scope

### IN M03

- Course kit AI generation: slides (≥8/unit), quizlets (≥2/unit), assignments (classwork / homework / case_study), teaching plan, lesson plans, teaching resources
- Faculty speaker notes on slides (FACULTY/ADMIN only; omitted for DEAN)
- Answer keys stored server-side only; never sent to client for any role
- Assignments include rubrics with weighted criteria
- CO mapping (co_reference) on slides, quizlets, and assignments
- Faculty editing, versioning, fork workflow
- Approval state machine: DRAFT → AI_GENERATING → DRAFT → PUBLISHED → ARCHIVED; fork any state → new DRAFT
- Compliance check before publish: SLIDE_MIN_NOT_MET (ERROR blocks), NO_TEACHING_PLAN (WARN advisory)
- One PUBLISHED kit per (syllabus_id, unit_number) — service-layer constraint
- Export: PPTX (faculty deck with speaker notes) + PDF (faculty slide deck, role-aware)
- Export: Student Handout PDF — sanitized, watermarked; no speaker_notes / answer_key / model_answer / rubric
- Async AI generation (Celery heavy queue)
- Audit logging (~22 events including export and handout events)

### OUT (deferred to M06 Labs Evaluator)

- AI detection for student submissions (perplexity / burstiness / RoBERTa)
- Threshold configuration per institution
- Evidence panel and flagged-submission workflow
- Faculty escalation pipeline: Dismiss / Warn / Escalate
- Locked-browser controlled assessment environment
- Copy-paste disabled in assessment UI
- Watermarked assessment session (UI overlay)
- Live quizlet sessions, quizlet responses, student submission tracking

## RBAC

| Action | ADMIN | FACULTY | DEAN |
|--------|-------|---------|------|
| Generate / Publish / Archive / Fork | ✓ | ✓ | ✗ |
| Edit DRAFT content | ✓ | ✓ | ✗ |
| View kit | ✓ | ✓ | ✓ |
| See speaker_notes / answer_key / model_answer | ✓ | ✓ | ✗ |
| Export (PPTX / PDF / Handout) | ✓ | ✓ | ✓ |

## Non-Negotiable Rules

- System never applies grade, penalty, or rejection autonomously
- Every consequential action requires human ratification
- Audit log is append-only
- answer_key NOT NULL in DB; never exposed via API to DEAN or student
- Multi-tenant isolation: every query scoped by tenant_id

## Step Log

| Step | Scope | Status | Commit |
|------|-------|--------|--------|
| STEP-01 | Config + StorageEntityType.COURSE_KIT_EXPORT + scaffold | COMPLETE | 3713957 |
| STEP-02 | DB models (4 tables, 5 enums) + Alembic migration 0007ten | COMPLETE | d4cdc51 |
| STEP-03 | Pydantic schemas (32 classes, faculty-only field gating) | COMPLETE | 83dda22 |
| STEP-04 | Repository layer (4 classes, 42 methods) | COMPLETE | fe11cd8 |
| STEP-05 | AI provider Protocol + GeminiCourseKitProvider + GroqCourseKitProvider | COMPLETE | c8a6b83 |
| STEP-06 | Celery task: course_kit_generation (heavy queue) | COMPLETE | e471c19 |
| STEP-07 | Service layer (29 methods) + router (29 endpoints), audit events | COMPLETE | 5590fcd + 52c5ddc + 199dc2c |
| STEP-10 | Export task: PPTX + PDF (python-pptx + reportlab), 46/46 smoke | COMPLETE | d5ae667 |
| STEP-11 | Backend tests (~70: compliance unit, service integration, router RBAC) | COMPLETE | 00c4543 |
| STEP-12 | Frontend API client + React Query hooks + TypeScript types | COMPLETE | 2166ff0 |
| STEP-13 | Frontend pages + components (16 files) | COMPLETE | 9673567 |
| STEP-14 | Frontend polish: skeleton, delete-confirm, version history, DEAN guard | COMPLETE | f5ac8bb |
| STEP-15 | Final QA pass — 4 demo-blocker fixes | COMPLETE | 3efd88f |
| STEP-15b | Soft-start: MinIO error → warning (no raise) | COMPLETE | 144a2b2 |
| STEP-15c | Groq normalizer fix 1 | COMPLETE | 7b877e1 |
| STEP-15d | Groq normalizer fix 2 | COMPLETE | 89275a7 |
| STEP-16 | Student handout PDF export (sanitized, watermarked) | COMPLETE | — |
| STEP-17 | Task file creation + memory update | COMPLETE | — |
| **MANUAL QA** | Full demo flow: Login → Syllabus → Generate → Export (all 3 formats) | PENDING | — |

## Key Architecture Decisions

- `kit_slides`, `kit_quizlets`, `kit_assignments`: separate normalized tables (support individual item regeneration)
- `teaching_plan`, `lesson_plans`, `resources`: JSONB on `course_kits` (no separate tables)
- `answer_key` on `kit_quizlets`: NOT NULL JSONB; never returned to DEAN via any API endpoint
- `model_answer` on `kit_assignments`: nullable Text; FACULTY/ADMIN only
- `speaker_notes` on `kit_slides`: nullable Text; FACULTY/ADMIN only
- Compliance check before publish: SLIDE_MIN_NOT_MET blocks; NO_TEACHING_PLAN advisory
- One PUBLISHED kit per (syllabus_id, unit_number) via `has_published_for_unit`
- Student handout export uses prefixed ReportLab style names (`ho_*`) to avoid collision with faculty PDF styles
- Windows asyncio fix on all Celery workers: `asyncio.WindowsSelectorEventLoopPolicy`

## Export Format Summary

| format | Content | Roles | File |
|--------|---------|-------|------|
| `pptx` | Full deck: slides + speaker notes + teaching plan + resources | ADMIN, FACULTY (notes stripped for DEAN) | `kit_{code}_u{n}_v{v}.pptx` |
| `pdf` | Faculty slide deck: all content, role-aware sensitive field gating | ADMIN, FACULTY, DEAN (DEAN sees no notes/answers) | `kit_{code}_u{n}_v{v}.pdf` |
| `handout` | Student handout: slide bullets + quizlet questions (no answers) + assignment questions (no rubric) + diagonal watermark | ADMIN, FACULTY, DEAN | `kit_{code}_u{n}_v{v}_handout.pdf` |

## Migration Chain

`0001 → 0002 → 0003 → 0004 → 0005 (M01) → 0006 (M02) → 0007 (M03)`

## Downstream Consumers

- M05 (Learning Materials): independent sibling, consumes PUBLISHED kits
- M06 (Labs Evaluator): consumes assignments; owns full assessment + submission pipeline
