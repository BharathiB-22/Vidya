# Vidya — Development History

Owner: Srinivas / Fidelitus Corp
Last updated: 2026-06-08

This file consolidates the sprint-by-sprint development history for the Vidya platform.
It replaces the `tasks/` directory and the `commit_msg_*.txt` session temp files.

---

## Phase 0 — Core Infrastructure (Weeks 1–6)

### TASK-000: Repository Initialisation
Status: COMPLETE (implied by all subsequent work)
- Docker Compose dev stack, PostgreSQL 16, Redis, MinIO
- GitHub Actions CI pipeline skeleton
- Coding standards and CLAUDE.md established

### TASK-001: Auth Module
Status: COMPLETE — all 14 steps, on master (2026-05-06)
Path: `backend/app/core/auth/`
- JWT access + refresh token rotation
- OTP-based password reset
- RBAC dependencies (`require_roles`)
- Schema-per-tenant isolation from day one
- `X-Tenant-Slug` header for tenant context on unauthenticated endpoints
- `password_changed_at` column prevents reset-token reuse

Key decisions:
- D-01: Schema-per-tenant (not row-level isolation) — PRD requirement
- D-02: X-Tenant-Slug header (not subdomain) for Phase 0
- D-03: Active user check every request (no stale-role window)
- D-05: slowapi rate limiting (self-contained, no gateway dependency)

Commit: `686227a` (BUG-H13 fix, 121/121 auth tests)

### TASK-002: Tenants Module
Status: COMPLETE (2026-05-06) — 22/22 tests
Path: `backend/app/core/tenants/`
- Tenant CRUD, schema provisioning, slug management
- Soft-delete with PERMANENTLY_DELETED status
- Known risk: Alembic env.py caching after tenant creation

### TASK-003: Audit Log Module
Status: COMPLETE (2026-05-07) — all 7 steps, 15/15 tests
Path: `backend/app/core/audit_log/`
Commit: `a9e766c`
- Append-only `public.audit_logs` table — no UPDATE or DELETE ever
- DB trigger enforces immutability at database level (deferred BUG-H04-07)
- AuditEventType enum covers all modules (grows per module)
- SUPER_ADMIN: all logs; tenant ADMIN: own tenant only

### TASK-007: Monitoring and Logging
Status: COMPLETE (2026-05-07) — 5 phases
Commit: `6232bff`
- Structured JSON logging (structlog)
- Health probes: /health/live, /health/ready, /health/full
- PII masking in log output
- Prometheus metrics endpoint

---

## Phase 1 — Teach & Prepare

### TASK-M01: Program Structure Advisor
Status: ALL 16 STEPS + stabilisation COMPLETE
Path: `backend/app/modules/m01_program_advisor/`
Commit: `91533ca`
- Groq primary provider (llama-3.3-70b), Gemini fallback
- AI generates program structure; Dean must approve (human gate)
- 28 ai_provider tests, Generate with AI verified
- Integration with AcadProgram via nullable FK (INT-1, commit `15c6e12c`)

### TASK-M02: Syllabus Generator
Status: IMPLEMENTATION-COMPLETE & DEMO-READY (2026-05-14)
Path: `backend/app/modules/m02_syllabus/`
Commit HEAD: `34f3556`
- Groq provider validated end-to-end
- Dean approve/reject governance (H-33)
- WARN-1: audit_logs FK non-blocking (known, deferred)

### TASK-M03 (TASK-012): Course Kit Builder
Status: CLOSED — implementation complete, demo-ready (2026-05-15)
Path: `backend/app/modules/m03_course_kit/`
- Celery heavy queue for AI generation
- PPT export (python-pptx), quiz generation, assignment types
- Groq + Gemini providers with fallback
- Redis confirmed; correct Windows Celery startup: `--pool=solo`

### TASK-M05 (TASK-013): Learning Material Packager
Status: ALL 17 STEPS COMPLETE (2026-05-16) — 166/166 tests
Path: `backend/app/modules/m05_learning_materials/`
Commit: `52c2e56`
- YouTube, arXiv, NPTEL, MIT OCW source aggregation
- Qdrant RAG with Google text-embedding-004
- Notebook Q&A with source citations
- Faculty can curate (add/remove) with "Faculty Recommended" flag

---

## Phase 2 — Assess & Research

### TASK-M06 (TASK-014): Labs & Assignment Evaluator
Status: CLOSED (2026-05-29) — 74/74 tests, 8/8 PRD ACs
Path: `backend/app/modules/m06_labs_evaluator/`
Commit: `451a3f53`
- WRITTEN and CODE assignment types with rubric and test cases
- AI evaluation via Celery (Gemini → Groq fallback)
- AI content detection (configurable threshold: AI_DETECTION_THRESH=0.75)
- Dean access to all evaluations; CLOSED report; file upload support

### TASK-M07 (TASK-015): Research Supervision
Status: ALL 18 STEPS COMPLETE (2026-05-18) — 41/41 tests
Path: `backend/app/modules/m07_research_supervision/`
Commit: `d249423`
- Guide assigned at proposal submit time
- ArXiv TF-IDF for novelty scoring; LLM for feasibility + clarity
- Human Gate 1: guide decides ACCEPT/REVISE/REJECT
- Async viva session support; DPDP compliant

### TASK-M08: Exam Setter
Status: ALL 18 STEPS COMPLETE (2026-05-18) — 75/75 tests
Path: `backend/app/modules/m08_exam_setter/`
Commit: `bb59aec`
- AI paper generation with Fernet AES sealing (paper locked until release)
- 3 human gates: generate → seal → release
- PDF export with watermark (H-35 productization, 211/211 tests)
- Commit after productization: `ad5aac34`

### TASK-M09 (TASK-M09): Paper Administration
Status: ALL 17 STEPS COMPLETE (2026-05-18) — 112/112 tests
Path: `backend/app/modules/m09_paper_admin/`
Commit: `37a22cb`
- Scanned script upload → AI scoring (Celery) → evaluator marks → Board gate
- Student identity masking: random `masked_id` token per script
- Append-only score ledger (no UPDATE after finalisation)
- 2 human gates: evaluator marks entry + Board finalisation

### TASK-M10: Bell Curve Normaliser
Status: ALL 18 STEPS COMPLETE (2026-05-19) — 94/94 tests
Path: `backend/app/modules/m10_bell_curve/`
Commit: `7dbf0f1`
- Statistical normalisation advisory only — no autonomous grade writing
- Board Gate 1 before any normalised score is persisted
- 4 frontend pages; fairness report

---

## Phase 2.5 — Infrastructure & SaaS Hardening

### H-03: KIND Cluster Stabilisation
Status: COMPLETE — commit `6780f27`
- KIND-10 config, all 10 pods healthy
- Ingress: vidya.127.0.0.1.nip.io live

### H-04: Full SaaS Smoke Testing
Status: COMPLETE (2026-05-20) — all 13 areas PASS
Commits: `41ea35a` → `aebe3c7`
- 4 bugs fixed; `get_tenant_context_dep` added
- BUG-H04-07 (audit append-only DB trigger) deferred

### H-05: Production Hardening
Status: COMPLETE (2026-05-21) — all 11 steps
- Secrets management, Helm values structure
- PENDING SRINIVAS: rotate keys, fill CHANGE_ME, set KUBE_CONFIG_STAGING

### H-07: Phase 2 Local Ops
Status: ALL STEPS COMPLETE (2026-05-23)
- H07-14: 58 E2E tests
- H07-15: 4 docs (walkthrough, demo script, readiness summary, QA checklist)
Commits: `767db53` → `dd326c9`

### H-16: Final SaaS Polish
Status: CLOSED (2026-05-23)
Commits: `2b78d95` → `43c3946`
- Nav gaps, onboarding bug, forgot-password, landing UX, QA script
- All 20 Playwright screenshots PASS

### H-17: SaaS Walkthrough QA
Status: CLOSED (2026-05-25) — commit `82b2bf5`
- 15 sub-tasks; audit metadata fix; 174/178 M05 tests
- RAG + Q&A validated; RBAC + tenant isolation confirmed

### H-28: Enterprise UI Productization
Status: CLOSED (2026-05-26) — commit `789aeeb1`
- Login / sidebar / dashboard / topbar rebrand

### H-29: SherpaVector Platform Console v2
Status: CLOSED (2026-05-26)
- Full rebrand both sides; migration `0007pub`
- AdminDashboard; SettingsBrandingPage; VIDYA AI rename

### H-30: UI Standardisation Sprint
Status: PHASES A/B/C/D COMPLETE (2026-05-27)
Commits: `1ed2598d` + `36900d4f`
- Phase E (SettingsBrandingPage + mobile) deferred

### H-33: Governance and Content Quality
Status: COMPLETE (2026-05-28) — 106+72 tests pass
- Dean-only approve/reject; faculty assignment scoping
- AI quality gates: 5+ units, richer topics; kit richness
- Migration `0023ten` required

### H-34: Academic Structure Stabilisation
Status: CLOSED (2026-05-29)
Commit: `73e36a62`
- Assignment module + RBAC fix; onboarding CSV import
- Migrations `0019ten`/`0020ten`/`0022ten`; `upgrade_all_tenants` tool

### H-35: M08 Exam Setter Productization
Status: ALL 14 STEPS COMPLETE — 211/211 tests
Commit: `ad5aac34`
- PDF export with watermark; CLOSED (2026-05-30)

### H-38: M06 Productization
Status: COMPLETE
- Instructions field + problem statement + course context + publish guard
- 82 tests; migration `0026ten`

### H-41: Super Admin Portal Polish + Tenant Delete
Status: COMPLETE
Commits: `a5afa57c` / `d244f667`
- UI polish + soft-delete + slug confirmation; 53 tenant tests

---

## Phase 3 — Student Information System (SIS)

### H-46 to H-48: SIS Foundation Polish
- H-46: Profile mgmt, platform branding, deleted tenants page — commit `8e27820b`
- H-47: Tenant login page production-ready, WCAG contrast — commit `2dc1c36e`
- H-48: Role-based sidebar, product labels, empty states, dashboard cleanup

### TASK-M11-001: SIS Foundation
Status: Phase 1 CLOSED (2026-06-01)
Commit: `0028ten`
- `sis_schools` table; School → Department FK
- `acad_*` tables are canonical SIS hierarchy
- 32 tests

### TASK-M11-002: SIS Enrollment Centre
Status: CLOSED (2026-06-01) — commit `47dd1f95`
- Roster + enroll + move + unenroll + profile + dashboard
- 61 tests; `UNIQUE(student_id)` invariant

### H-50: SIS Students & Faculty Directory
Status: CLOSED (2026-06-03) — commit `25c7c58a` + BUG-H50-01 fix
- USN/employee_id profiles; paginated directory
- 7 API endpoints, 4 frontend pages; 102/102 tests
- BUG-H50-01: AuthGuard split for FACULTY role

### H-51: Student & Faculty Self-Service Profile
Status: CLOSED (2026-06-03) — commit `2920c998`
- `me_router`, `MyProfilePage`, strict field-level RBAC
- No new tables; 122/122 tests

### H-52: SIS Notifications
Status: CLOSED (2026-06-03) — commit `838f5bcc`
- 7 notification triggers; 20 tests; 142/142 SIS pass

### H-53: SIS Bulk Profile Import
Status: CLOSED (2026-06-03) — commit `ee2dd534`
- CSV/XLSX import; preview + commit; partial success
- 167/167 tests

### H-54: SIS Semester Rollover
Status: CLOSED (2026-06-03) — 193/193 tests
- 2-phase preview + commit; ADMIN only; no new tables

### H-55: Attendance Management
Status: CLOSED (2026-06-03) — 249/249 tests
- 2 tables (`0031ten`); 13 routes; 3 frontend pages
- 48h edit window from `first_marked_at`

### H-56: Shortage Detection
Status: CLOSED (2026-06-03) — commit `a4a58970` — 286/286 tests
- No new tables; 44 total routes; faculty shortage page
- Grouped analytics; sessions-needed calculator; `finalized_only` param

### H-57: Internal Marks Management
Status: CLOSED (2026-06-05) — commit `e60375b9`
- Migration `0032ten`; faculty mark entry; Dean report

### H-58: Hall Ticket Eligibility
Status: CLOSED (2026-06-05) — commit `607d0313`
- DRAFT/PUBLISHED workflow; engine + override + batch
- Migration `0033ten`; 76 tests

### H-59: Examination Management
Status: CLOSED (2026-06-05) — commit `ee79cbd4`
- 4 tables (`0034ten`); 24 routes; 97 tests
- SEATING_ALLOCATED lifecycle; 7 frontend screens

### H-60: Results Management
Status: CLOSED (2026-06-05)
Commits: `9d8f5a1d` (backend) + `554afb64` (frontend)
- 7 tables (`0035ten`); 36 routes; 7 pages; 627 tests
- 5 human gates; student portal with grade card

### H-61: Transcript Generation
Status: CLOSED (2026-06-08) — commit `3012c596`
- 4 tenant tables + public index (`0036ten`, `0012pub`)
- 13 routes + public verify; Celery PDF; QR code
- 152/152 tests

### H-62: Graduation Audit & Certificate Generation
Status: CLOSED (2026-06-08) — commit `01defeee`
- 4 tenant tables + public index (`0037ten`, `0013pub`)
- 19 tenant routes + public cert verify (no auth)
- EligibilityEngine: 8 advisory flags (never autonomous)
- 4 human gates: Dean submit → Board ratify → Board approve → Registrar issue
- `CERT/{TENANT_CODE}/{YEAR}/{SEQ:06d}` via PostgreSQL sequence
- Privacy: `_partial_name()` — never exposes full name publicly
- `board_resolution_ref` mandatory in validator AND service double-check
- 196/196 tests

---

## Open Items & Integration Gaps

The following are known architectural gaps documented for future H-series work:

1. **M09 ↔ SIS Bridge** — `exam_score_ledger` (M09) and `sis_external_marks` (SIS) are parallel
   tables not yet connected. Scanned paper marks do not auto-populate SIS result declarations.

2. **M10 ↔ SIS Bridge** — Bell-curve normalised scores do not flow to SIS grade cards.

3. **CO-PO Attainment** — No module computes CO attainment from M06/M09/SIS results, despite
   M02 defining CO-PO mappings.

4. **Quizlet Live Session** — M03 generates static quizlets; real-time response capture is not built.

5. **OCR/Scanning System** — `detect_scan_quality.py` and `ocr_scanned_script.py` workers exist
   under M09. A full scanning pipeline (camera → OCR → mark sheet) is the next Phase 3 candidate.
