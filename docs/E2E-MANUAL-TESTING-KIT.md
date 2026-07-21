# VIDYA — End-to-End Manual Testing Kit (QA & Stabilization)

> **Master kit.** Supersedes `docs/EXAM-MODULE-TEST-KIT.md` (folded in as the Question Paper /
> Internal Assessment / Board modules below). Single source of truth for full-platform manual QA.
>
> **Execution protocol (agreed):** test **one module at a time**, in the order below. On the
> first failure in a module → **stop**, report the Test ID + role + expected vs actual → I fix
> only that bug → **re-test the whole module** → do not advance until the module is fully green.
> Repeat until every module passes. Final commit only after the entire platform passes.
>
> **You execute; I do not fabricate results.** Tick `[x] Pass` / `[x] Fail` per case.

---

## 0. Global preconditions (once, before any module)

- [ ] **Apply all tenant migrations to the latest HEAD revision before starting manual testing.**
      Do not stop at a specific revision — always migrate the ABC tenant schema to HEAD
      (e.g. via Admin → Tenant Migrations, or `alembic upgrade head` for the tenant schema).
      A schema left one revision behind HEAD will fail tests with missing-column errors.
- [ ] Services up: **Postgres, Redis, API (FastAPI), Celery heavy worker, frontend**.
      *(Celery worker is mandatory for AI paper generation, course-kit generation, and exports.)*
- [ ] `EXAM_FERNET_KEY` set to a valid 44-char Fernet key (else sealed papers can't survive a
      worker restart).
- [ ] **At least one AI key** set (`GEMINI_API_KEY` / `DEEPSEEK_API_KEY` / `GROQ_API_KEY`).
      m08 falls back to a syllabus-aware mock; **m03 has no mock** — without a key, course-kit
      generation fails and decks come out empty.
- [ ] S3/MinIO reachable (`S3_ENDPOINT`, bucket `vidya-assets`) for course-kit exports, research
      docs, assignment files.

> **If any manual test fails because a database column is missing, first verify the tenant schema
> is migrated to HEAD before investigating application code.**

### Roles in the platform
`ADMIN · DEAN · FACULTY · STUDENT · BOARD · GUIDE · EVALUATOR`. RBAC is enforced on the **active
workspace** (`viewing_role`), sent via the `X-Active-Workspace` header — a multi-responsibility
account (e.g. a Faculty holding a Board grant) is treated as whatever workspace is active.

### Recommended module execution order (dependency-first)
1. Authentication & RBAC → 2. Institution Management → 3. Academic Management → 4. Faculty →
5. Students → 6. Governance → 7. Course Kits → 8. Assignments → 9. Research Supervision →
10. Question Papers → 11. Internal Assessment → 12. Board Workflow → 13. Analytics →
14. Notifications → 15. Settings → 16. Workspace Switching.

### Per-case field legend
`Test ID · Module · Preconditions · Steps · Expected · DB impact · APIs · Roles allowed · Pass/Fail`

---

## Module 1 — Authentication & RBAC

**AUTH-01 — Login (valid)**
- Preconditions: a provisioned user exists (admin).
- Steps: POST credentials on the login screen.
- Expected: access + refresh tokens returned; redirected to role dashboard.
- DB impact: none (read); `audit_logs` login event.
- APIs: `POST /auth/login`, `GET /auth/me`.
- Roles: all.
- [ ] Pass  [ ] Fail

**AUTH-02 — Login (invalid password)**
- Steps: wrong password.
- Expected: 401, generic error; no token issued.
- DB impact: none. APIs: `POST /auth/login`. Roles: all.
- [ ] Pass  [ ] Fail

**AUTH-03 — Token refresh & logout**
- Steps: refresh token; then logout; then reuse old token.
- Expected: refresh returns new tokens; after logout the token is rejected (401).
- DB impact: refresh-token store invalidated. APIs: `POST /auth/refresh`, `POST /auth/logout`.
- Roles: all. [ ] Pass  [ ] Fail

**AUTH-04 — /me returns roles + responsibilities**
- Expected: `MeResponse` lists base role + any grants (responsibilities) + available workspaces.
- APIs: `GET /auth/me`. Roles: all. DB: read. [ ] Pass  [ ] Fail

**AUTH-05 — Change password**
- Steps: change password; re-login with new password.
- Expected: old password rejected, new accepted. APIs: `POST /auth/change-password`.
- DB: `users.password_hash` updated. Roles: all. [ ] Pass  [ ] Fail

**AUTH-06 — RBAC deny (cross-role)**
- Steps: as STUDENT, call a faculty-only route (e.g. create exam paper) directly.
- Expected: 403.
- APIs: any `require_roles`-guarded route. Roles: negative test. [ ] Pass  [ ] Fail

**AUTH-07 — Password reset flow**
- Steps: request reset → verify code → confirm new password.
- Expected: each step succeeds; login works with new password.
- APIs: `POST /auth/password-reset/{request,verify,confirm}`. DB: reset token rows. [ ] Pass [ ] Fail

---

## Module 2 — Institution Management

**INST-01 — Create tenant "ABC University"**
- Preconditions: platform/super-admin session.
- Steps: create tenant (name, slug, logo optional).
- Expected: tenant row created, schema provisioned, migrations run to head.
- DB impact: `public.tenants` row; new `tenant_<slug>` schema; `tenant_migration_log`.
- APIs: `POST /tenants`. Roles: platform admin. [ ] Pass  [ ] Fail

**INST-02 — Tenant provisioning / migration status**
- Steps: view migrations status.
- Expected: ABC's current revision matches the latest Alembic HEAD, status success.
- APIs: `GET /tenants/migrations`, `GET /tenants/{id}`. DB: read. Roles: platform admin.
- [ ] Pass  [ ] Fail

**INST-03 — Admin login into tenant**
- Steps: log in as the ABC tenant admin.
- Expected: admin dashboard loads scoped to ABC only.
- APIs: `POST /auth/login`. Roles: ADMIN. [ ] Pass  [ ] Fail

**INST-04 — Tenant isolation**
- Steps: as ABC admin, attempt to read another tenant's data (e.g. by id).
- Expected: not visible / 403/404 — never cross-schema.
- DB: queries scoped by `search_path`. Roles: negative. [ ] Pass  [ ] Fail

**INST-05 — Branding (logo / primary colour)**
- Steps: set institution branding.
- Expected: branding persists; appears on login + PPTX cover.
- APIs: `PATCH /auth/branding`, `POST /auth/branding/logo`. DB: `tenants.logo_url/primary_color`.
- Roles: ADMIN. [ ] Pass  [ ] Fail

---

## Module 3 — Academic Management

**ACAD-01 — Create Department**
- Preconditions: ADMIN.
- Steps: create department (e.g. CSE).
- Expected: department created and listed.
- DB: `departments`. APIs: `POST /academics/departments`. Roles: ADMIN/DEAN. [ ] Pass [ ] Fail

**ACAD-02 — Create Program**
- Steps: create program (e.g. B.E. CSE) under the department.
- Expected: program created; visible in Programs list.
- DB: `programs` (+ acad program). APIs: `POST /programs` and/or `POST /academics/programs`.
- Roles: ADMIN/DEAN. [ ] Pass  [ ] Fail

**ACAD-03 — Batch → generate semesters → sections**
- Steps: create batch (e.g. 2025–29) → generate semesters → add a section.
- Expected: 8 semesters generated; section created.
- DB: `batches`, `semesters`, `sections`.
- APIs: `POST /academics/batches`, `POST /academics/batches/{id}/generate-semesters`, `POST /academics/sections`.
- Roles: ADMIN. [ ] Pass  [ ] Fail

**ACAD-04 — Create Course/Subject with auto code**
- Steps: add course (e.g. Data Structures) to the program.
- Expected: course created with generated code (e.g. CS301); appears in course list.
- DB: `courses`. APIs: `POST /programs/{program_id}/courses`, `GET /programs/courses`.
- Roles: ADMIN/DEAN. [ ] Pass  [ ] Fail

**ACAD-05 — Program AI generation → submit → publish (governance)**
- Steps: generate program outcomes/curriculum with AI → submit → (governance approve) → publish.
- Expected: statuses advance; publish blocked until governance approves (see Governance module).
- DB: `programs.status`, `program_outcomes`. APIs: `POST /programs/{id}/generate|submit|publish`.
- Roles: ADMIN/DEAN + BOARD (approve). [ ] Pass  [ ] Fail

**ACAD-06 — Syllabus for a course (approved) — REQUIRED downstream**
- Steps: create/generate a syllabus for CS301 with ≥3 units (titles+topics) and ≥2 COs; approve/lock it.
- Expected: syllabus status LOCKED/APPROVED; units + COs present.
- DB: `syllabi`, `syllabus_units`, `course_outcomes`. APIs: `/syllabi/*`.
- Roles: FACULTY/DEAN/BOARD per governance. **Blocks Course Kits + Question Papers if missing.**
- [ ] Pass  [ ] Fail

---

## Module 4 — Faculty

**FAC-01 — Create/import faculty**
- Steps: import faculty via CSV (preview → commit) or create individually.
- Expected: faculty users created with FACULTY role; institution emails generated.
- DB: `users`, `faculty_profiles`. APIs: `POST /admin/onboarding/import/faculty/{preview,commit}`.
- Roles: ADMIN. [ ] Pass  [ ] Fail

**FAC-02 — Assign faculty to a course/subject**
- Steps: assign the faculty to CS301.
- Expected: faculty now "teaches" CS301 (drives `faculty_teaches_course`).
- DB: course-assignment table. APIs: `/course-assignments/*` (or academics allocation).
- Roles: ADMIN/DEAN. [ ] Pass  [ ] Fail

**FAC-03 — Assign faculty to a program (dean-scope / responsibilities)**
- Steps: assign faculty to a program; optionally grant a role (e.g. BOARD/EVALUATOR).
- Expected: assignment + grant recorded; new workspace becomes available to that faculty.
- DB: `faculty_program_assignments`, faculty role grants.
- APIs: `POST /admin/onboarding/faculty-programs/assign`, `POST /admin/onboarding/faculty-roles/grant`.
- Roles: ADMIN. [ ] Pass  [ ] Fail

**FAC-04 — Faculty login & scope**
- Steps: log in as the faculty.
- Expected: sees only their assigned subjects; cannot see unassigned courses' management actions.
- Roles: FACULTY. [ ] Pass  [ ] Fail

---

## Module 5 — Students

**STU-01 — Generate / import students**
- Steps: generate students for a section, or CSV import (preview → commit).
- Expected: student users created; USNs assigned.
- DB: `users`, `student_profiles`. APIs: `POST /admin/onboarding/generate-students`,
  `/import/students/{preview,commit}`. Roles: ADMIN. [ ] Pass  [ ] Fail

**STU-02 — Student login & enrolment scope**
- Steps: log in as a student.
- Expected: sees only enrolled courses' published content (kits, assignments).
- Roles: STUDENT. [ ] Pass  [ ] Fail

**STU-03 — USN / institution-email backfill**
- Steps: run USN backfill preview → commit.
- Expected: missing USNs filled; no duplicates.
- APIs: `/admin/onboarding/usn-backfill/{preview,commit}`. DB: `student_profiles.usn`. Roles: ADMIN.
- [ ] Pass  [ ] Fail

---

## Module 6 — Governance

**GOV-01 — Governance queue visible to Board**
- Preconditions: a submitted program/syllabus awaiting approval.
- Steps: as BOARD, open governance queue.
- Expected: pending item appears with readiness summary.
- APIs: `GET /governance/queue`, `GET /governance/programs/{id}/readiness`. Roles: BOARD/ADMIN.
- [ ] Pass  [ ] Fail

**GOV-02 — Publish-readiness gate**
- Steps: view publish-readiness for a program with an unmet requirement.
- Expected: readiness reports the gap; publish blocked.
- APIs: `GET /governance/programs/{id}/publish-readiness`. Roles: BOARD/ADMIN. [ ] Pass [ ] Fail

**GOV-03 — Board approves (single approve gate)**
- Steps: as BOARD, approve the program/syllabus.
- Expected: status → approved; publish now permitted. No "reject/return" path (approve is the gate).
- DB: approval request rows; `programs/syllabi.status`. APIs: `POST /governance/programs/{id}/approve`.
- Roles: BOARD/ADMIN. [ ] Pass  [ ] Fail

**GOV-04 — Approval trail is append-only**
- Steps: view the approval trail/history.
- Expected: immutable trail of who approved when; no edits/deletes.
- APIs: `GET /governance/programs/{id}/trail|history`. DB: `audit_logs` append-only. [ ] Pass [ ] Fail

**GOV-05 — Non-Board cannot approve**
- Steps: as FACULTY/DEAN (no board grant), attempt approve.
- Expected: 403. Roles: negative. [ ] Pass  [ ] Fail

---

## Module 7 — Course Kits (incl. AI PPT lifecycle — Task 2)

**CK-01 — Create kit + Generate with AI**
- Preconditions: CS301 has an approved syllabus (ACAD-06); AI key set.
- Steps: create kit for a unit → **Generate with AI**.
- Expected: status AI_GENERATING → DRAFT; ~10 slides (Title/Objectives/Concept/Definition/Worked
  Example/Code|Diagram/Common Mistakes/Activity/Quiz/Summary) + assignments populated.
- DB: `course_kits`, `kit_slides`, `kit_assignments`; `audit_logs`.
- APIs: `POST /course-kits`, `POST /course-kits/{id}/generate`, `GET /course-kits/{id}/jobs/{jobId}`.
- Roles: FACULTY/ADMIN. [ ] Pass  [ ] Fail

**CK-02 — Edit slides / assignments**
- Steps: edit a slide, reorder, add/delete an assignment (DRAFT only).
- Expected: changes persist; edits blocked once not DRAFT.
- DB: `kit_slides`, `kit_assignments`. APIs: `/course-kits/{id}/slides|assignments/*`. Roles: FACULTY.
- [ ] Pass  [ ] Fail

**CK-03 — Publish kit**
- Steps: publish.
- Expected: status PUBLISHED; students in the course can now see it; export enabled.
- DB: `course_kits.status`, `published_at`. APIs: `POST /course-kits/{id}/publish`. Roles: FACULTY/DEAN.
- [ ] Pass  [ ] Fail

**CK-04 — Export PPTX + download**
- Steps: Exports → New Export (pptx) → Refresh → Download.
- Expected: real professional .pptx downloads (native editable shapes, tenant branding, tables, diagrams).
- DB: `storage_assets` (entity `course_kit_export`). APIs: `POST /course-kits/{id}/export`,
  `GET /course-kits/{id}/exports`, `GET /course-kits/{id}/exports/{asset}/download`. Roles: FACULTY.
- [ ] Pass  [ ] Fail

**CK-05 — Edit in PowerPoint then Upload Deck** *(Task 2)*
- Steps: edit the .pptx locally → Exports → **Upload Deck** → pick file.
- Expected: uploaded deck appears as a new export asset in the same list; downloads identically.
- DB: new `storage_assets` (`course_kit_export`). APIs: `POST /course-kits/{id}/exports/upload-url`,
  `POST /course-kits/{id}/exports`. Roles: FACULTY/ADMIN (write). [ ] Pass  [ ] Fail

**CK-06 — Replace deck** *(Task 2)*
- Steps: on an export row → **Replace (↺)** → pick a newer file.
- Expected: old asset removed, new one present — **one** row, not two.
- DB: old `storage_assets` soft-deleted, new inserted. APIs: `POST /exports` with `replace_asset_id`.
- Roles: FACULTY/ADMIN. [ ] Pass  [ ] Fail

**CK-07 — Delete deck** *(Task 2)*
- Steps: on an export row → **Delete (🗑)**.
- Expected: asset disappears from list; its download URL no longer resolves.
- DB: `storage_assets.deleted_at` set (S3 reclaimed by retention job).
- APIs: `DELETE /course-kits/{id}/exports/{asset}`. Roles: FACULTY/ADMIN. [ ] Pass  [ ] Fail

**CK-08 — Regenerate**
- Steps: Generate with AI again, then re-export.
- Expected: fresh slides + new export produced. Roles: FACULTY. [ ] Pass  [ ] Fail

**CK-09 — RBAC: read-only viewer**
- Steps: as DEAN (read) open Exports.
- Expected: **Download** visible; **Upload/Replace/Delete hidden** (and 403 if forced).
- Roles: negative/read. [ ] Pass  [ ] Fail

**CK-10 — Reject non-deck upload**
- Steps: Upload Deck → choose a .txt.
- Expected: rejected (MIME whitelist) with a clear error. [ ] Pass  [ ] Fail

**CK-11 — No-AI-key behaviour (config check)**
- Steps: with AI keys unset, generate.
- Expected: generation fails clearly (no silent empty kit); surfaced to faculty. [ ] Pass  [ ] Fail

---

## Module 8 — Assignments (incl. evaluator workflow)

**ASG-01 — Faculty creates assignment**
- Preconditions: FACULTY assigned to the course; optionally nominate evaluator(s).
- Steps: create assignment (DRAFT), set evaluator(s).
- Expected: created DRAFT; `evaluator_user_ids` stored.
- DB: `assignments`. APIs: `POST /assignments`. Roles: FACULTY/ADMIN. [ ] Pass  [ ] Fail

**ASG-02 — Publish → student submits**
- Steps: publish; as STUDENT submit a file.
- Expected: status PUBLISHED; student submission stored.
- DB: `assignments.status`, `assignment_submissions`, `storage_assets`.
- APIs: `POST /assignments/{id}/publish`, `POST /assignments/student/{id}/submit`.
- Roles: FACULTY then STUDENT. [ ] Pass  [ ] Fail

**ASG-03 — Submit for evaluation → allocate evaluator**
- Steps: faculty submits the assignment for evaluation; Admin/Dean allocates an evaluator per submission.
- Expected: status SUBMITTED; evaluator assigned; appears in evaluator's "My Work".
- DB: `assignments.status=SUBMITTED`, `evaluation_assignments`.
- APIs: `POST /assignments/{id}/submit`, `POST /assignments/submissions/{sid}/evaluator`,
  `GET /assignments/evaluator/my-work`. Roles: FACULTY + ADMIN/DEAN, then EVALUATOR. [ ] Pass [ ] Fail

**ASG-04 — Evaluator grades → faculty finalizes (human gate)**
- Steps: EVALUATOR grades a submission; FACULTY finalizes the assignment.
- Expected: grades recorded; **FINALIZED** only via faculty action (never auto).
- DB: `assignment_submissions.grade`, `assignments.status=FINALIZED`, `finalized_by_user_id`.
- APIs: `PATCH /assignments/submissions/{sid}/grade`, `POST /assignments/{id}/finalize`.
- Roles: EVALUATOR then FACULTY. [ ] Pass  [ ] Fail

**ASG-05 — Student sees result after finalize**
- Steps: as STUDENT open result.
- Expected: grade/feedback visible only after finalize.
- APIs: `GET /assignments/student/submissions/{sid}/result`. Roles: STUDENT. [ ] Pass  [ ] Fail

**ASG-06 — RBAC: evaluator scope**
- Steps: EVALUATOR tries to grade a submission not allocated to them.
- Expected: 403 / not visible. Roles: negative. [ ] Pass  [ ] Fail

---

## Module 9 — Research Supervision

**RES-01 — Guide proposes/approves problem**
- Preconditions: a GUIDE user; a research student linked.
- Steps: GUIDE AI-proposes problems → stores one → student picks or guide decides.
- Expected: problem created; decision recorded (approve/return).
- DB: `research_problems`. APIs: `POST /research/problems/propose|ai-store`, `POST /research/problems/{id}/decide`.
- Roles: GUIDE. [ ] Pass  [ ] Fail

**RES-02 — Student submits document → guide reviews**
- Steps: STUDENT uploads a document to a problem; GUIDE reviews.
- Expected: doc stored; review status set (no autonomous acceptance).
- DB: `research_documents`, `storage_assets`. APIs: `POST /research/student/documents`,
  `POST /research/documents/{id}/review`. Roles: STUDENT then GUIDE. [ ] Pass  [ ] Fail

**RES-03 — Viva schedule → conduct → ratify (human gate)**
- Steps: create viva → conduct → ratify.
- Expected: viva result recorded only via explicit human ratify.
- DB: `viva_sessions`. APIs: `POST /research/vivas`, `.../conduct`, `.../ratify`. Roles: GUIDE/BOARD.
- [ ] Pass  [ ] Fail

**RES-04 — Guides list / student scope**
- Steps: student views only their own problems/documents.
- Expected: no cross-student visibility. APIs: `/research/student/*`. Roles: STUDENT. [ ] Pass [ ] Fail

---

## Module 10 — Question Papers (creation, AI/manual, PDF)

**QP-01 — Faculty creates AI paper (INTERNAL)**
- Preconditions: approved syllabus; Celery worker up.
- Steps: create paper (exam_type INTERNAL, workflow INTERNAL, AI), pick units/blueprint/template, Bloom sums 100.
- Expected: 202; status Generating → Generated. Questions present.
- DB: `exam_papers`, `exam_questions`, `blooms_compliance_reports`.
- APIs: `POST /exams`, `GET /exams/jobs/{jobId}`. Roles: FACULTY/ADMIN/BOARD (create). [ ] Pass [ ] Fail

**QP-02 — Manual paper**
- Steps: create with creation_mode MANUAL; add questions by hand (respect template blocks).
- Expected: lands directly in GENERATED (no Celery); questions saved `ai_generated=false`; a question
  with no `template_block_id` on a templated paper is rejected.
- DB: `exam_papers`, `exam_questions`. APIs: `POST /exams`, `POST /exams/{id}/questions`. Roles: FACULTY.
- [ ] Pass  [ ] Fail

**QP-03 — Edit / regenerate / reorder / duplicate**
- Steps: edit a question, regenerate one (async), reorder, duplicate.
- Expected: all persist while GENERATED/BOARD_RETURNED only.
- APIs: `PATCH/DELETE /exams/{id}/questions/{qid}`, `POST .../regenerate|duplicate`, `PUT .../reorder`.
- Roles: FACULTY. [ ] Pass  [ ] Fail

**QP-04 — Download PDF before submission**
- Steps: at GENERATED, export PDF.
- Expected: print-ready PDF (sections, marks, OR-choices, no model answers).
- APIs: `GET /exams/{id}/export/pdf`. Roles: FACULTY/DEAN/BOARD/ADMIN. [ ] Pass  [ ] Fail

**QP-05 — Delete draft (allowed states)**
- Steps: delete a paper in DRAFT / GENERATED / BOARD_RETURNED.
- Expected: deletes (cascades questions). SUBMITTED/APPROVED/SEALED/RELEASED/**FAILED** → blocked (409).
- DB: `exam_papers` (+cascade). APIs: `DELETE /exams/{id}`. Roles: creator/ADMIN. [ ] Pass [ ] Fail

**QP-06 — Semester-End creation restricted to Board** *(Task 1)*
- Steps: as FACULTY create exam_type **END_SEM**.
- Expected: **403** ("created by the Board only"). As BOARD → succeeds.
- APIs: `POST /exams`. Roles: negative (FACULTY) / BOARD. [ ] Pass  [ ] Fail

---

## Module 11 — Internal Assessment Workflow (Dean-gated — Task 1)

**IA-01 — Submit to Dean**
- Preconditions: INTERNAL paper, GENERATED, ≥1 question.
- Steps: FACULTY clicks Submit.
- Expected: status → **Submitted to Dean**; **Delete + edit disappear** (read-only for faculty);
  paper enters Dean pending queue; governing Dean notified.
- DB: `exam_papers.status=SUBMITTED`, `submitted_at`; `notifications`.
- APIs: `POST /exams/{id}/submit`, `GET /exams/dean/pending`. Roles: FACULTY. [ ] Pass  [ ] Fail

**IA-02 — Dean returns for corrections → faculty resubmits**
- Steps: DEAN returns with a comment; FACULTY edits; resubmits.
- Expected: status → BOARD_RETURNED (shown "Dean Returned"); editable again; resubmits to Dean.
- APIs: `POST /exams/{id}/dean-decision` (approved=false, comment). Roles: DEAN then FACULTY.
- [ ] Pass  [ ] Fail

**IA-03 — Dean approves**
- Steps: DEAN approves.
- Expected: status → BOARD_APPROVED (shown "Dean Approved"); faculty can no longer edit.
- DB: `approved_by/at`. APIs: `POST /exams/{id}/dean-decision` (approved=true). Roles: DEAN. [ ] Pass [ ] Fail

**IA-04 — Dean locks (seals)** *(Task 1)*
- Steps: DEAN opens the paper → **Lock**, set planned release date.
- Expected: status → SEALED; questions inaccessible (403 SEALED_ACCESS); **no auto-release scheduled**.
- DB: `sealed_at`, `release_at`, `encrypted_blob_key`; `release_job_id` **NULL**.
- APIs: `POST /exams/{id}/seal`. Roles: **DEAN**/ADMIN (Faculty → 403). [ ] Pass  [ ] Fail

**IA-05 — Dean releases (manual only)** *(Task 1)*
- Steps: wait past planned time → confirm still SEALED → DEAN clicks **Release Now**.
- Expected: **no automatic release** occurred; release happens only on Dean action → RELEASED.
- DB: `released_at`. APIs: `POST /exams/{id}/release`. Roles: **DEAN**/ADMIN (Faculty → 403). [ ] Pass [ ] Fail

**IA-06 — Faculty cannot finalize internal** *(Task 1 RBAC)*
- Steps: as FACULTY attempt `/seal` and `/release`.
- Expected: **403** ("Only the Dean can lock or release an internal assessment paper").
- Roles: negative. [ ] Pass  [ ] Fail

**IA-07 — Faculty self-approve removed** *(Task 1)*
- Steps: call `POST /exams/{id}/faculty-approve`.
- Expected: **404** (endpoint removed). Roles: negative. [ ] Pass  [ ] Fail

**IA-08 — Internal marks: faculty submit → Dean lock**
- Steps: FACULTY enters internal marks and submits; DEAN locks.
- Expected: PENDING → FACULTY_SUBMITTED → DEAN_LOCKED (immutable after); total computed on submit.
- DB: `internal_marks_summary`. APIs: `POST /exams/internal-marks/{id}/submit|lock`. Roles: FACULTY/DEAN.
- [ ] Pass  [ ] Fail

---

## Module 12 — Board Workflow

**BRD-01 — Faculty submits Board paper to Board**
- Preconditions: BOARD_EXAM workflow paper, GENERATED.
- Steps: FACULTY submits.
- Expected: status SUBMITTED → **Board** pending queue (not Dean).
- APIs: `POST /exams/{id}/submit`, `GET /exams/board/pending`. Roles: FACULTY. [ ] Pass [ ] Fail

**BRD-02 — Board reviews with model answers**
- Steps: BOARD opens the paper's questions with answers.
- Expected: model answers/marking scheme visible to BOARD/ADMIN only.
- APIs: `GET /exams/{id}/questions/with-answers`. Roles: BOARD/ADMIN (Faculty/Dean → 403). [ ] Pass [ ] Fail

**BRD-03 — Board returns / approves**
- Steps: return (comment required) → faculty resubmits → Board approves.
- Expected: approve → BOARD_APPROVED and **questions promoted to question bank** (`is_approved`).
- DB: `question_bank`. APIs: `POST /exams/{id}/board-decision`. Roles: BOARD. [ ] Pass  [ ] Fail

**BRD-04 — Board locks → releases (manual)**
- Steps: BOARD Lock (seal) → Release Now.
- Expected: SEALED then RELEASED; no auto-release.
- APIs: `POST /exams/{id}/seal`, `POST /exams/{id}/release`. Roles: BOARD/ADMIN (Faculty → 403).
- [ ] Pass  [ ] Fail

**BRD-05 — Optional scrutinizer (Gate 1.5)**
- Steps: BOARD assigns a scrutinizer to a SUBMITTED paper; scrutinizer approves/returns.
- Expected: approve keeps SUBMITTED; return → BOARD_RETURNED.
- APIs: `POST /exams/{id}/assign-scrutinizer|scrutinize`. Roles: BOARD then assigned FACULTY.
- [ ] Pass  [ ] Fail

**BRD-06 — Workflow isolation**
- Steps: as BOARD, view `/exams/all` and board pending.
- Expected: INTERNAL papers are **never** visible to the Board. Roles: negative. [ ] Pass [ ] Fail

**BRD-07 — Export released paper**
- Steps: after RELEASED, export questions PDF; export answers (faculty/board/admin only).
- Expected: students may get questions only; answers never exposed to students.
- APIs: `GET /exams/{id}/export/{pdf,questions,answers}`. [ ] Pass  [ ] Fail

---

## Module 13 — Analytics

**AN-01 — Role dashboards load**
- Steps: open dashboard as ADMIN, DEAN, FACULTY, STUDENT, BOARD.
- Expected: each dashboard renders role-appropriate widgets, no cross-role data leak, no errors.
- Roles: all. [ ] Pass  [ ] Fail

**AN-02 — Exam analytics / Bloom compliance**
- Steps: open exam analytics for a course/paper.
- Expected: Bloom distribution, CO/unit coverage reflect generated papers.
- APIs: `/exam-analytics/*`, `GET /exams/{id}/blooms|coverage`. Roles: FACULTY/DEAN/BOARD. [ ] Pass [ ] Fail

**AN-03 — Ownership / shortage / compliance widgets**
- Steps: open ownership dashboard + faculty-shortage report + exam-compliance.
- Expected: figures reconcile with the data created above; export works where offered.
- APIs: `/academics/*` (ownership), `/exam-compliance/*`. Roles: ADMIN/DEAN. [ ] Pass  [ ] Fail

**AN-04 — Empty-state correctness**
- Steps: open a dashboard for a brand-new entity with no data.
- Expected: graceful empty state, not an error/crash. [ ] Pass  [ ] Fail

---

## Module 14 — Notifications

**NOT-01 — Internal paper submission notifies Dean**
- Steps: FACULTY submits an INTERNAL paper (IA-01).
- Expected: governing Dean receives a "paper awaiting review" notification.
- DB: `notifications`. APIs: `GET /notifications`. Roles: DEAN. [ ] Pass  [ ] Fail

**NOT-02 — Mark read / read-all**
- Steps: mark one read; then read-all.
- Expected: unread count updates correctly.
- APIs: `PATCH /notifications/{id}/read`, `POST /notifications/read-all`. Roles: all. [ ] Pass [ ] Fail

**NOT-03 — Notification failure never blocks the action**
- Steps: (if reproducible) submit while notification backend is degraded.
- Expected: submission still succeeds; notification is best-effort. [ ] Pass  [ ] Fail

---

## Module 15 — Settings

**SET-01 — Attendance edit window (configurable)**
- Steps: as ADMIN set the attendance edit window; verify enforcement on a faculty edit outside it.
- Expected: edits blocked outside window per config. Roles: ADMIN/FACULTY. [ ] Pass  [ ] Fail

**SET-02 — Calendar / holidays**
- Steps: view seeded national holidays; add a university holiday; add a personal event.
- Expected: holidays present (from the national-holidays seed migration); events persist; student calendar reflects them.
- DB: calendar/event tables. APIs: `POST /calendar/events`, `POST /calendar/me/events`,
  `GET /calendar/me`. Roles: ADMIN (institution), all (personal). [ ] Pass  [ ] Fail

**SET-03 — Institution domain / email config**
- Steps: set institution email domain; preview generated addresses.
- Expected: domain saved; generated emails follow it.
- APIs: `PUT /admin/onboarding/institution-domain`, `/institution-email/preview`. Roles: ADMIN.
- [ ] Pass  [ ] Fail

**SET-04 — Branding persists (cross-check INST-05)**
- Expected: branding used consistently (login, PPTX). [ ] Pass  [ ] Fail

---

## Module 16 — Workspace Switching (multi-responsibility RBAC)

**WS-01 — Switch workspace changes viewing_role**
- Preconditions: a faculty with an extra grant (e.g. BOARD or DEAN or EVALUATOR).
- Steps: switch active workspace in the UI.
- Expected: `X-Active-Workspace` sent; actions available match the **active** workspace, not the base role.
- APIs: header `X-Active-Workspace` on all calls; `GET /auth/me` lists workspaces. Roles: multi-grant.
- [ ] Pass  [ ] Fail

**WS-02 — Faculty-workspace actions for a base DEAN/BOARD**
- Steps: base DEAN with FACULTY grant acts in the Faculty workspace on their own paper.
- Expected: Faculty actions (Delete/Submit/Edit) appear and work; server authorizes on `viewing_role`.
- [ ] Pass  [ ] Fail

**WS-03 — Switching away removes privileges**
- Steps: switch from BOARD workspace to FACULTY workspace, then attempt a board-only action.
- Expected: board-only actions hidden and 403 if forced (privilege follows the active workspace).
- Roles: negative. [ ] Pass  [ ] Fail

**WS-04 — Internal finaliser needs the Dean workspace** *(ties Task 1)*
- Steps: a DEAN-granted user in the FACULTY workspace tries to Lock an internal approved paper.
- Expected: hidden/403; switching to the DEAN workspace enables Lock/Release. [ ] Pass  [ ] Fail

---

## Sign-off

| Module | Result | Notes |
|---|---|---|
| 1 Authentication & RBAC | ☐ Pass ☐ Fail | |
| 2 Institution Management | ☐ Pass ☐ Fail | |
| 3 Academic Management | ☐ Pass ☐ Fail | |
| 4 Faculty | ☐ Pass ☐ Fail | |
| 5 Students | ☐ Pass ☐ Fail | |
| 6 Governance | ☐ Pass ☐ Fail | |
| 7 Course Kits | ☐ Pass ☐ Fail | |
| 8 Assignments | ☐ Pass ☐ Fail | |
| 9 Research Supervision | ☐ Pass ☐ Fail | |
| 10 Question Papers | ☐ Pass ☐ Fail | |
| 11 Internal Assessment | ☐ Pass ☐ Fail | |
| 12 Board Workflow | ☐ Pass ☐ Fail | |
| 13 Analytics | ☐ Pass ☐ Fail | |
| 14 Notifications | ☐ Pass ☐ Fail | |
| 15 Settings | ☐ Pass ☐ Fail | |
| 16 Workspace Switching | ☐ Pass ☐ Fail | |

**Final commit only after every module above is Pass.**

> When a case fails, report: `Test ID · active role/workspace · expected · actual (message/status/screenshot)`.
> I will fix only that bug, then you re-test the whole module before advancing.
