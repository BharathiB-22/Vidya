# Academic Governance — Current State, Gaps, and Recommended Architecture

**Status:** Analysis only. No code changes.
**Date:** 2026-07-11
**Scope:** Programs / Curriculum, Syllabus, Faculty Assignment, Electives, Timetable, Approvals.

---

## 1. Current Workflow

### 1.1 Who is who

| Actor | Where they live | How they are authenticated |
|---|---|---|
| **Super Admin** | `public.platform_users` (no tenant) | JWT with `schema_name = null`; `require_roles()` short-circuits — **Super Admin bypasses every role check** and can enter any tenant by sending `X-Tenant-Slug`. |
| **Admin** (institution) | tenant `users.role = ADMIN` | Standard tenant JWT. |
| **Dean** | tenant `users.role = DEAN` | Scoped by `dean_program_assignments`. |
| **Faculty** | tenant `users.role = FACULTY` | Scoped by `subject_assignments` / `faculty_program_assignments`. |
| **Student** | tenant `users.role = STUDENT` | Scoped by `acad_enrollments`. |
| **Board** | tenant `users.role = BOARD` **and/or** a `faculty_role_grants` row with `role_code = 'BOARD'` | Used **only** in examination governance (M08/M09/M10). Has **no curriculum authority today**. |

### 1.2 Curriculum (Program) approval flow — `m01_program_advisor`

```
Dean/Admin creates Program (DRAFT)
        │
        ├─ POST /generate  ──►  Celery worker (program_structure.py)
        │                        writes courses/outcomes and sets status
        │                        directly to PENDING_APPROVAL  ← no human submit
        ▼
   PENDING_APPROVAL
        │  POST /approve   (require_roles(DEAN))   → runs compliance gate
        ▼
     APPROVED
        │  POST /publish   (require_roles(DEAN))
        ▼
     PUBLISHED  ── terminal, read-only. Courses only now become
                   assignable and count toward Academic Ownership.
                   Changing anything requires fork() → new version.
```

Two things stand out:

* **The AI worker, not a human, moves the program into the approval queue** (`workers/heavy/program_structure.py:469`). Nobody signs "I propose this."
* **The same Dean creates, approves, and publishes.** There is one human gate, but no second human. `POST /reject` also has no comment column on `programs` — it silently drops the program back to `DRAFT`.

### 1.3 Syllabus flow — `m02_syllabus` (the healthiest flow in the codebase)

```
Faculty drafts / AI-generates  →  DRAFT
Faculty submits (compliance gate, faculty_teaches_course check)  →  PENDING_REVIEW
Dean approves                                                    →  DEAN_APPROVED
Dean locks (freeze for semester)                                 →  DEAN_LOCKED
Dean rejects (with dean_comment)                                 →  REJECTED → resubmit
```

This is a genuine two-party maker/checker flow: author = Faculty, approver = Dean.

### 1.4 Timetable flow — `core/timetable`

```
DRAFT → submit → PENDING_REVIEW → approve → APPROVED → publish → PUBLISHED
```

**All four endpoints (`/submit`, `/approve`, `/reject`, `/publish`) are `require_roles(TenantRole.DEAN)`.** A single Dean builds the timetable, submits it to herself, approves it, and publishes it. The state machine looks like governance but enforces none.

### 1.5 Electives

Dean creates elective *slots* (`elective_baskets`, curriculum-weighted once), hangs option courses off them, assigns faculty per option, then drives `DRAFT → PUBLISHED → OPEN → CLOSED`. Students register for exactly one option while the slot is `OPEN`.

### 1.6 Existing Board implementation

Board exists — but only downstream of teaching:

| Where | What Board does |
|---|---|
| M08 exam setter | Gate 2: `exam_papers.status → BOARD_APPROVED / BOARD_RETURNED` |
| M09 paper admin | `exam_board_sessions` + `exam_board_course_approvals`: Dean **convenes** → Board **approves/rejects** → Admin **declares** |
| M10 bell curve | `BELL_CURVE_BOARD_RATIFIED` |
| M11 graduation | `GRADUATION_AUDIT_BOARD_APPROVED` |

**`exam_board_sessions` is the only real committee model in the system**, and it is the right shape: convene → decide → declare, with an append-only audit trail. It is the pattern to generalize.

### 1.7 Role switching (Dean ↔ Faculty)

**There is none.** No impersonation, no "act as", no role switcher in the frontend (`grep` for `switchRole|activeRole|actingRole|impersonate` returns nothing).

What exists instead is `faculty_role_grants`: one account, base `users.role`, plus N active responsibility grants (`GUIDE`, `EVALUATOR`, `BOARD`, `DEAN`). `require_responsibility()` passes on *base role OR active grant*.

The problem is that **only `m02_syllabus` uses `require_responsibility`.** Every governance router — `m01`, `timetable`, `ownership`, `elective`, `marks`, `attendance` — uses `require_roles`, which reads the base role column only. So a Faculty with an active `DEAN` grant gets *no* Dean powers anywhere it matters, and onboarding contradicts the model further by minting `DEAN`/`BOARD` as **standalone primary accounts with no faculty profile** (`onboarding/service.py:975, 1217`). The grant system is built but effectively unused for governance.

---

## 2. Existing Database

### 2.1 Relevant tables (all in the tenant schema unless noted)

| Concern | Tables |
|---|---|
| Identity / roles | `public.platform_users`, `users` (single `role` enum column), `faculty_role_grants` |
| Org structure (ERP) | `acad_departments`, `acad_programs`, `acad_batches`, `acad_semesters`, `acad_sections`, `acad_enrollments` |
| Curriculum (versioned doc) | `programs` (`version`, `parent_version_id`, `status`), `program_outcomes`, `courses`, `course_prerequisites` |
| Electives | `elective_baskets` (the curriculum slot), `elective_registrations` (student's one choice) |
| Syllabus | `syllabi`, `course_outcomes`, `co_po_mappings`, `syllabus_units`, `syllabus_references` |
| Faculty assignment | `subject_assignments` (course+semester, PRIMARY/CO_FACULTY/GUEST), `faculty_program_assignments` (teaching scope), `dean_program_assignments` (governance scope) |
| Timetable | `timetables`, `timetable_slots`, `timetable_templates`, `timetable_periods` |
| Assessment | `sis_marks_components`, `sis_marks_entries`, attendance tables, `exam_*` |
| Governance (exams only) | `exam_board_sessions`, `exam_board_course_approvals` |
| Audit | `audit_logs` (append-only; has `PROGRAM_APPROVED`, `SYLLABUS_APPROVED`, `SUBJECT_ASSIGNMENT_CREATED`, …) |

> **Note the two "program" concepts.** `acad_programs` = the administrative program (MCA, its batches and sections). `programs` = the versioned *curriculum document*, linked by `programs.acad_program_id`. Approval state lives on the curriculum document. This split is good and should be preserved.

### 2.2 Does the schema support Board / University approval?

**No — it needs extension, but not a rewrite.** Every approval today is a **single-actor column pair** stamped onto the entity:

```
programs   : approved_by_user_id, approved_at, published_by_user_id, published_at
syllabi    : approved_by_user_id, approved_at, locked_by_user_id, locked_at, dean_comment
timetables : reviewed_by_user_id, reviewed_at, review_comment, published_by_user_id
```

Missing at the schema level: any notion of a **body**, **membership**, **multi-stage chain**, **quorum/votes**, **meeting/resolution reference**, or **effective-from date**. There is no generic approval table — `exam_board_sessions` is hard-wired to `exam_paper_id`.

---

## 3. Role Analysis — what each role actually controls today

| Role | Controls | Notably does **not** control |
|---|---|---|
| **Super Admin** | Tenants, provisioning, migrations, platform branding. Bypasses all tenant role checks. | — (unbounded by design; worth revisiting) |
| **Admin** | User onboarding & bulk import, USN/faculty-code allocation, all `acad_*` master data, **grants BOARD/GUIDE/EVALUATOR**, marks lock/reopen, exam declaration. | Curriculum approval is shared with Dean, not exclusive. |
| **Dean** | **Almost everything academic.** Creates + approves + publishes curriculum; approves + locks syllabi; builds + approves + publishes timetables; assigns faculty to programs and subjects; runs elective slots; locks/reopens marks; reopens attendance; convenes exam boards. Scoped to `dean_program_assignments`. | Board-gated exam approvals. |
| **Faculty** | Syllabus authoring, course kits, assignments, labs, attendance marking, internal marks entry — scoped to `subject_assignments`. | Any approval. Cannot see another faculty's course. |
| **Student** | Elective choice, own timetable/subjects/attendance/marks/results. | — |
| **Board** | Exam paper Gate-2, results board sessions, bell-curve ratification, graduation audit. | **Curriculum, syllabus, timetable, faculty assignment — zero involvement.** |

**The finding in one line: `DEAN` is currently a single-role conflation of HOD + Board of Studies + Academic Council + Timetable Committee + Controller of Examinations.**

---

## 4. Real University Comparison

| Question | Real university (Indian, UGC/NBA context) | VIDYA today | Verdict |
|---|---|---|---|
| Who **creates** curriculum? | Course faculty / subject expert drafts; HOD consolidates. | Dean or Admin creates; **AI worker** fills it in. | Faculty are not authors of the curriculum. |
| Who **approves** curriculum? | **Board of Studies (BoS)** → **Academic Council** → (Univ. Statutes / Syndicate for affiliated colleges). Multi-member, quorum, minutes, resolution number, effective regulation year. | **The same Dean who created it.** | **Biggest gap.** |
| Who **owns** syllabus? | The curriculum (BoS-approved) owns the syllabus. Faculty own the *lesson plan / course file* under it. | Faculty author the syllabus; Dean approves and locks. | Close, but no BoS above the Dean, and no lesson-plan/syllabus separation. |
| Who **assigns** faculty? | HOD proposes workload; Dean/Principal ratifies. | Dean or Admin, directly. | Acceptable; missing the HOD proposal step. |
| Who **manages** timetable? | Timetable Committee / Academic Coordinator prepares; HOD + Dean approve; Registrar publishes. | Dean does all four steps alone. | State machine exists but is a no-op. |
| Who **manages** attendance & internal marks? | Faculty record; HOD verifies; Dean/CoE locks; Exam Section publishes. | Faculty record; Dean/Admin lock and reopen. | **Reasonable — leave alone.** Internal assessment is genuinely department-owned. |

---

## 5. Gap Analysis

**Governance structure**
1. No **Board of Studies** or **Academic Council** in the curriculum path. `BOARD` exists as a role but is exam-only.
2. No **HOD / Department Chair** role. The HOD → BoS → Council chain is collapsed into `DEAN`.
3. No **committee model** for curriculum: no body, membership, quorum, votes, meeting date, or resolution/minutes reference. (Exams have one; curriculum does not.)

**Separation of duties**
4. **Dean self-approves curriculum** (creator = approver = publisher) and **self-approves timetables** (all four endpoints are `DEAN`). This satisfies the letter of "human ratification" but not its intent.
5. **No human submit step on programs** — the Celery worker sets `PENDING_APPROVAL`, so AI output enters the approval queue with no human proposer. This is the clearest conflict with the "AI advises, humans decide" rule.

**Data model**
6. No **regulation / scheme year** (R2024) and no **effective-from batch** binding a curriculum version to the students it governs. `programs.version` exists but is not tied to an academic year or batch.
7. No **generic approval workflow tables** — approvals are denormalized columns, so a second or third stage cannot be represented at all.
8. No **rejection reason on programs** (`syllabi.dean_comment` has one; `programs` does not).
9. No **post-publish amendment** path. `PUBLISHED` is terminal; the only route is `fork()`, with no recorded amendment reason or approving body.

**Roles & access**
10. **`require_responsibility` is used by exactly one module.** Every governance router reads the base role column, so `faculty_role_grants` — the mechanism that would let a professor sit on the BoS — is inert where it matters.
11. **No Dean ↔ Faculty context switch.** A Dean who also teaches cannot act as Faculty; onboarding even denies `DEAN`/`BOARD` accounts a faculty profile.
12. Super Admin bypasses every tenant role gate, including approvals.

---

## 6. Recommendations

**Guiding principle: add a governance *layer*, do not rewrite the workspaces.** Dean, Faculty and Student workspaces stay exactly as they are. They keep reading `approved_by_user_id` / `status` as they do today.

### 6.1 Generalize the exam-board pattern into `core/governance`

Four new tenant-schema tables, modelled directly on `exam_board_sessions` (which already works):

```
approval_bodies        (id, body_type: BOS | ACADEMIC_COUNCIL | TIMETABLE_COMMITTEE | EXAM_BOARD,
                        scope_program_id | scope_department_id, is_active)

approval_body_members  (body_id, user_id, member_role: CHAIR | CONVENER | MEMBER,
                        is_active, granted_by, granted_at, revoked_by, revoked_at)
                        ← soft-revoke, identical to faculty_role_grants

approval_requests      (id, entity_type: PROGRAM | SYLLABUS | TIMETABLE, entity_id,
                        body_id, stage, status, submitted_by, submitted_at,
                        meeting_ref, resolution_no)     ← polymorphic, one row per stage

approval_decisions     (request_id, decided_by, decision: APPROVE | REJECT | ABSTAIN,
                        comment, decided_at)            ← append-only; quorum computed from this
```

**Keep the existing `approved_by_user_id` / `approved_at` / `status` columns** on `programs`, `syllabi`, `timetables` as the denormalized *final decision*. The governance layer writes them on final approval. **Result: zero breakage in the existing UI and services.**

### 6.2 Reuse the `BOARD` role — do not add a new `TenantRole`

`TenantRole.BOARD` already exists, is already grantable via `faculty_role_grants`, already has frontend pages (`BoardReviewPage`, `BoardCompliancePage`), and already has audit event types. Extend it to curriculum rather than inventing a `UNIVERSITY_MEMBER` role.

Fix the contradiction: a BoS member in a real university **is a senior professor**. Board should be a *grant on a Faculty account*, not a standalone account (`onboarding/service.py` currently forbids this).

### 6.3 Correct the two governance defects

* **Program:** the worker should land on `DRAFT` (or a new `AI_DRAFTED`), and a **human must call `POST /submit`** to create the approval request. This restores "AI advises, humans decide" at the database level.
* **Separation of duties:** enforce `approver ≠ submitter` in the service layer plus a DB check constraint, with a per-tenant `governance_settings.self_approval_allowed` escape hatch for small single-college tenants.

### 6.4 Configurable approval chain

```
Faculty drafts course/syllabus
      ↓  submit
HOD / Dean consolidates and submits          ← stage 0 (optional, tenant-configurable)
      ↓
BOARD OF STUDIES  (quorum of BOARD grantees) ← stage 1
      ↓
ACADEMIC COUNCIL  (optional)                 ← stage 2
      ↓
PUBLISHED (effective from regulation year / batch)
```

`governance_settings(stages_enabled, quorum_required, self_approval_allowed)` lets a single-college tenant run this as a one-stage flow identical to today's behaviour, and a university tenant run the full chain — same code path.

### 6.5 Bind curriculum to a regulation

Add `regulation_year` and `effective_from_batch_id` to `programs`. Universities cannot answer "which syllabus applies to this student?" without it, and neither can VIDYA today.

### 6.6 Timetable — cheapest correct fix

Keep the Dean's builder UI untouched. Route `/submit` through `approval_requests` against a `TIMETABLE_COMMITTEE` body, or — as a minimum — enforce `approver ≠ creator`. Do not build a new workspace for this.

### 6.7 Role switching — resolve, don't switch

Do not build impersonation. Instead:
* Migrate the governance routers from `require_roles` to `require_responsibility` so the **effective permission set = base role ∪ active grants**.
* Add a frontend workspace switcher that only changes which navigation is rendered — no token change, no backend change. `faculty_role_grants` already backs it.

This gives Dean ↔ Faculty ↔ Board switching with **no schema change and no new role**.

### 6.8 Leave alone

Attendance and internal marks (Faculty records → Dean locks) already match real practice. Do not add a Controller of Examinations unless a tenant asks. The exam board flow (M08–M10) is correct and becomes the reference implementation, not a refactor target.

### 6.9 Suggested phasing (each phase independently shippable)

| Phase | Content | Risk |
|---|---|---|
| A | Governance tables + `governance_settings`, no behaviour change | None |
| B | Governance routers move to `require_responsibility`; Board grantable on Faculty accounts; frontend workspace switcher | Low |
| C | Program flow: human `submit`, BoS gate, `approver ≠ submitter` | Medium — changes the m01 state machine |
| D | Syllabus + timetable routed through the same approval engine | Low (syllabus already 2-party) |
| E | `regulation_year` / `effective_from_batch_id`; amendment workflow for published curricula | Medium |

All new tables are tenant-scoped; `audit_logs` stays append-only, with new event types (`BOS_APPROVED`, `COUNCIL_RATIFIED`, `CURRICULUM_AMENDED`) added to the existing enum.
