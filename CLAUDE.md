# CLAUDE.md - Vidya

# Extends global CLAUDE.md. Project-specific rules take precedence.

# Owner: Srinivas / Fidelitus Corp

## Stack

Python 3.12, FastAPI, Celery, Redis, React 18, TypeScript, Vite, shadcn/ui, Tailwind CSS, PostgreSQL 16, Qdrant, MinIO/S3, Gemini 1.5 Pro / 2.0 Flash, Docker, Kubernetes

## Current Phase

Current Phase: 0

Phase 0 = Foundation, Weeks 1 to 6.
Phase 1 = Teach and Prepare.
Phase 2 = Assess and Research.

## PRD Reference

Vidya-PRD.md in project root.
Always read the relevant feature section before building.

## Module Boundaries

One Claude session per module boundary.

### Phase 0 - Core Infrastructure

auh:
backend/app/core/auth/

tenants:
backend/app/core/tenants/

audit-log:
backend/app/core/audit-log/

task-queue:
backend/app/core/task-queue/

notifications:
backend/app/core/notifications/

storage:
backend/app/core/storage/

monitoring:
backend/app/core/monitoring/

### Phase 1 - Teach and Prepare

m01-program:
backend/app/modules/m01_program_advisor/

m02-syllabus:
backend/app/modules/m02_syllabus_gen/

m03-course-kit:
backend/app/modules/m03_course_kit/

m05-learning:
backend/app/modules/m05_learning_materials/

### Phase 2 - Assess and Research

m06-labs:
backend/app/modules/m06_labs_evaluator/

m07-research:
backend/app/modules/m07_research_supervision/

m08-exam:
backend/app/modules/m08_exam_setter/

m09-paper:
backend/app/modules/m09_paper_admin/

m10-bell:
backend/app/modules/m10_bell_curve/

### Special Sessions

debug:
One error and one file per session.

audit:
Read audit logs and AuditLog table queries only.

status:
Read task files, summarise progress, no code changes.

## Non-Negotiable Rules

* AI advises, humans decide.
* Never write code that applies a grade, penalty, or rejection autonomously.
* Every consequential action needs a human ratification step at the database level, not only in the UI.
* Audit log is append-only. No UPDATE or DELETE on the audit\_logs table ever.
* Multi-tenant isolation is mandatory.
* Never query across tenant schemas.
* Every query must include tenant\_id scoping.
* Async jobs only for AI generation.
* Never block the API thread for AI generation.
* All AI outputs must be logged to AuditLog.
* AuditLog should include model, prompt\_hash, output summary, and confidence score.

## Key Config

Fill before first session.

GEMINI\_API\_KEY = AIzaSyCxDoyH0istyuUdMb2pWN6x4huIUq7sTpQ

DATABASE\_URL = postgresql+asyncpg://vidya:vidya\_dev@localhost:5432/vidya

REDIS\_URL = redis://localhost:6379/0

S3\_ENDPOINT = http://localhost:9000

S3\_BUCKET = vidya-assets

JWT\_SECRET = 1889a2bea7f4c026f5b6922687e67b4a72c47780076bf12c0233b8e1f9624cca

ENVIRONMENT = development

AI\_DETECTION\_THRESH = 0.75

PLAGIARISM\_THRESH = 0.85Git

Branches:
main
dev
feature/TASK-XXX

Commit format:
\[TASK-XXX] verb: what changed

Never commit to main.
Srinivas reviews every PR before merge.

