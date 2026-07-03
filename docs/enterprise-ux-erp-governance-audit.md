# VIDYA AI — Enterprise UX, ERP Workflow & Governance Audit

**Analysis & planning only. No code was changed, no migrations created, no tests run.**
Grounded in the codebase at `C:\vidya`, branch `feature/erp-onboarding`, 2026-07-03.
Companion to the existing `docs/course_kit_learning_package_reality_audit.md` and `docs/governance-model.md`.

Every "Current State" claim is traceable to a file. Recommendations are proposals for future phases and must follow the workflow: **Plan → Approval → Implementation → Commit → Manual testing by the team.**

---

## 0. How the academic graph is actually modelled (shared foundation)

Everything in this audit sits on one graph. Understanding it removes 80% of the confusion in Modules 1 and 2.

```
acad_departments (CS, Computer Applications, ECE…)
   └─ acad_programs        (MCA, BCA, B.Tech CSE…)      FK department_id
        └─ acad_batches    (2024–2026 cohort)           FK program_id
             └─ acad_semesters (Sem 1..N)               FK batch_id
                  └─ acad_sections (A, B, C)             FK semester_id
                       └─ acad_enrollments (student→section)   FK section_id

courses                    (subject catalogue)          FK to syllabus/program elsewhere
subject_assignments        faculty ⇄ course ⇄ semester ⇄ section   (WHO TEACHES WHAT)
faculty_program_assignments faculty ⇄ program           (TEACHING/COORDINATOR SCOPE)
dean_program_assignments   dean ⇄ program               (GOVERNANCE SCOPE)
faculty_role_grants        faculty ⇄ {GUIDE,EVALUATOR,BOARD,DEAN}  (RESPONSIBILITIES)
sis_faculty_profile.primary_department_id               (HOME DEPARTMENT)
```

Source: `backend/app/modules/m_academics/models.py:38-355`.

Four *different* notions of "a faculty belongs to X" coexist, and they are frequently conflated in the UI:

| Concept | Table | Meaning | Cardinality |
|---|---|---|---|
| Home department | `sis_faculty_profile.primary_department_id` | The one department that "owns" the person | 1 |
| Program scope | `faculty_program_assignments` | Programs a faculty may teach/coordinate | N |
| Course teaching | `subject_assignments` | Actual course+semester+section a faculty teaches | N |
| Responsibilities | `faculty_role_grants` | GUIDE/EVALUATOR/BOARD/DEAN hats on one login | N |

This four-way split is the **root of Module 1 and Module 2 problems.** It is a reasonable ERP model; the defects are in how the graph is populated, joined, and surfaced — not in the schema shape.

---

# MODULE 1 — Faculty Responsibilities (incorrect information)

### Current State

- **Page**: `frontend/src/pages/faculty/FacultyResponsibilitiesPage.tsx`. Renders a Department → Program → Course hierarchy plus three stat cards (Departments/Programs/Courses).
- **Data hook**: `useFacultyResponsibilities()` → `GET` ownership responsibilities endpoint.
- **Backend**: `OwnershipService.get_faculty_responsibilities()` (`ownership_service.py:130-285`).

The endpoint assembles the page from **three independent SQL queries**:

1. **Explicit program scope** — `faculty_program_assignments` joined to `acad_programs` and, for the department, `LEFT JOIN acad_departments d ON d.id = COALESCE(fpa.department_id, ap.department_id)` (`ownership_service.py:139-155`).
2. **Implied programs** — programs derived from the courses actually taught: `subject_assignments → acad_semesters → acad_batches → acad_programs → acad_departments` (`ownership_service.py:185-225`).
3. **Course list** — `subject_assignments` resolved through the same batch→program→department chain, with those joins as `LEFT JOIN` so a course with a broken linkage still appears (`ownership_service.py:236-278`).

### Problems (root-cause analysis of "MCA faculty shows wrong program")

**Department is derived, not owned — and from a different source than the program.**
The department shown on the page is *not* the faculty's `primary_department_id`. It is the department of whatever *program* the faculty is attached to (`COALESCE(fpa.department_id, ap.department_id)`). Because MCA and the wrong program can both hang off "Department of Computer Applications", the department renders correctly while the program is wrong. The correct-looking department masks the bad program row.

**Three likely mechanisms for the wrong program, in priority order:**

1. **A stale/incorrect `faculty_program_assignments` row.** `assign_faculty_to_program` stamps `department_id` from the program at assign time and never re-syncs (`ownership_service.py:458-481`). If onboarding/backfill or a dean assigned the faculty to the wrong program (or a since-renamed program), that row is authoritative for query #1 and shows forever until soft-revoked. There is no validation that the assigned program's department matches the faculty's home department.
2. **Denormalised `fpa.department_id` drift.** `department_id` is copied onto the assignment row. If the program is later moved to another department (`acad_programs.department_id` changes), the assignment's stored `department_id` is now stale, and the `COALESCE` prefers the *stale* stamped value. Result: a program shown under the wrong department, or a right department with a program that no longer belongs to it.
3. **Backfill heuristics.** `faculty_program_service` / onboarding backfill derives program membership from "first resolved program at CSV import" (`docs/governance-model.md:38-40`). A faculty whose import row resolved to the wrong first program gets a wrong `faculty_program_assignments` seed.

**"Multiple responsibilities are not reflected."**
This page shows only *teaching* scope (programs + courses). The faculty's actual **responsibilities** — GUIDE / EVALUATOR / BOARD / DEAN from `faculty_role_grants` — are returned by a *completely different* endpoint (`me_router.py:49-64`, `GET /me/responsibilities`) and are **never rendered on this page.** So a faculty who is also a Guide and an Evaluator sees none of it here. The page is mis-titled "Academic Responsibilities" when it is really "Teaching Assignments." The word "Responsibilities" in the product means two different things in two different places.

**Secondary issues**
- Stat cards count array lengths client-side (`data.programs.length` etc.) while a *separate* `get_faculty_summary()` (`ownership_service.py:287-337`) computes counts via a UNION. Two code paths, two chances to disagree.
- `is_primary` (program coordinator) is surfaced as a "Primary" chip but there is no legend explaining coordinator vs. member.

### Recommendations (do not implement yet)

1. **Separate "identity" from "derived scope" on the page.** Header block = home department (`primary_department_id`) + responsibilities chips (`faculty_role_grants`). Body = derived teaching scope. One page, three clearly labelled zones: *Who I am*, *What I govern/assist with*, *What I teach*.
2. **Make department a first-class fact, not a `COALESCE` guess.** Prefer `sis_faculty_profile.primary_department_id` for the "home department" line; keep the program's department only for the per-program grouping. Never let a stale stamped `fpa.department_id` override the live `acad_programs.department_id` — drop the denormalised column from the read path (compute live) or add a reconciliation job.
3. **Add a data-integrity guard** at assignment time: warn (not block — AI advises, humans decide) when the assigned program's department ≠ faculty home department.
4. **Merge the two "responsibilities" endpoints** into one aggregate so teaching scope *and* role grants come back together and the page can render both.

### Proposed UX

```
My Academic Responsibilities
┌ Identity ───────────────────────────────────────────────┐
│ Dr. A. Kumar   FAC0042   Dept of Computer Applications   │
│ Responsibilities:  [FACULTY] [GUIDE] [EVALUATOR]         │
├ Programs I coordinate / teach in ───────────────────────┤
│ MCA (PG)  ·  Coordinator          3 courses             │
│ BCA (UG)                          1 course              │
├ Courses I teach ────────────────────────────────────────┤
│ MCA · Sem 2 · Sec A   CA201 Data Structures   PRIMARY   │
└──────────────────────────────────────────────────────────┘
```

### Proposed Architecture

- One read endpoint `GET /academics/faculty/{id}/responsibilities` returning `{ identity, responsibilities[], programs[], courses[] }`.
- `identity.department` from `primary_department_id`; `responsibilities` from `faculty_role_grants`; `programs`/`courses` derived as today but with live (non-stamped) department resolution.
- Optional nightly reconciliation task that flags `faculty_program_assignments` whose stamped `department_id` ≠ program's current department.

---

# MODULE 2 — Dean Academic Governance (Ownership Matrix / Faculty Programs / Course Assignments)

### Current State — purpose of each surface

| Page | File | Backs onto | Grain |
|---|---|---|---|
| **Course Assignments** | `pages/CourseAssignmentsPage.tsx` | `subject_assignments` (`assignment_service.py`) | faculty ⇄ **course + semester + section** |
| **Faculty Programs** | `pages/dean/DeanAssignFacultyProgramPage.tsx` | `faculty_program_assignments` (`ownership_service.assign_faculty_to_program`) | faculty ⇄ **program** |
| **Ownership Matrix** | `pages/dean/DeanOwnershipMatrixPage.tsx` | `OwnershipService.get_ownership_matrix()` (`ownership_service.py:678-826`) | **read-only projection** of `subject_assignments`, nested program → semester → course → faculty |
| (My Faculty) | `pages/dean/DeanMyFacultyPage.tsx` | `list_dean_faculty_assignments` + `get_faculty_workload` | roster view |

### Current workflow

- Dean governs a set of programs via `dean_program_assignments`; scope is enforced in `_require_dean_scope()` (`ownership_service.py:56-73`) on every mutating call. ADMIN/SUPER_ADMIN bypass.
- Dean assigns faculty to a **program** (Faculty Programs page) → `faculty_program_assignments` row.
- Dean/faculty assigns faculty to a **course** in a semester/section (Course Assignments) → `subject_assignments` row.
- Ownership Matrix simply *reads* `subject_assignments` and displays them grouped — it creates nothing.

### Problems — overlap analysis

**Is the Ownership Matrix generated from Course Assignments? — Yes, already.**
`get_ownership_matrix()` reads only `subject_assignments` (+ programs/semesters/courses/users) and never `faculty_program_assignments` (`ownership_service.py:743-826`). It is a pure read model. So "Ownership Matrix" and "Course Assignments" are **the same data, two presentations**: one editable list, one nested read-only grid. That's acceptable ERP practice (a worklist + a coverage matrix), but today they are presented as two peer navigation items with overlapping names, which reads as duplication.

**Does Faculty Programs duplicate Course Assignments? — Partially, and confusingly.**
- A faculty who teaches `CA201` in MCA is *implicitly* in the MCA program — and the responsibilities endpoint already derives that implication (`ownership_service.py:185-225`). So for pure "is this faculty in this program" membership, `faculty_program_assignments` is **redundant with what `subject_assignments` already implies.**
- `faculty_program_assignments` carries **two things `subject_assignments` cannot**: (a) `is_primary` = program coordinator, and (b) program membership *before any course exists* (useful during onboarding). Those are real, non-duplicate responsibilities.
- The redundancy is that program membership is now stored in two places and can disagree: a faculty can have an active `faculty_program_assignments` row for MCA but zero MCA courses, or teach MCA courses with no program row. The responsibilities/summary code papers over this with UNION logic (`ownership_service.py:300-337`), which is a smell.

### Recommendations — one responsibility per page

Give each surface a single job:

1. **Course Assignments = the only place you edit who teaches what.** Grain: course + semester + section. Source of truth for teaching. (Keep.)
2. **Ownership Matrix = read-only coverage/gap view** built from Course Assignments — highlight *unassigned* courses (coverage gaps) and *over-loaded* faculty. Rename to "Teaching Coverage" to kill the "matrix vs assignments" confusion. (Keep, reframe as analytics not data-entry.)
3. **Faculty Programs = coordinator & program-membership governance only.** Narrow it to: appoint/*retire* a **program coordinator** (`is_primary`) and grant program membership for onboarding-before-courses. Stop presenting it as a second way to "assign teaching." Everything else (which courses) flows from Course Assignments.
4. **Reconcile the two membership sources.** Treat `subject_assignments` as authoritative for *teaching membership* and `faculty_program_assignments` as authoritative only for *coordinator + pre-course membership*. The responsibilities view should show "member (via courses)" vs "coordinator (appointed)" distinctly rather than UNION-flattening them.

### Proposed UX

- Dean landing → **Teaching Coverage** (matrix, read-only, gap-highlighted) as the hero.
- "Assign teaching" action opens **Course Assignments** filtered to the dean's programs.
- "Coordinators" is a small tab inside program settings, not a peer nav item.

### Proposed Architecture

- No schema change required. Add a `source` discriminator in the responsibilities read model (`APPOINTED` vs `IMPLIED`).
- Add a coverage query: per program/semester, `courses` LEFT JOIN `subject_assignments` WHERE assignment IS NULL → unassigned list. This makes the matrix a *governance* tool, not a mirror.

---

# MODULE 3 — Notification System

### Current State (what exists — verified)

**Infrastructure is real and solid.** `backend/app/core/notifications/`:
- Table `notifications` (`models.py:40-64`): recipient, type (free string), title, body, `entity_type`/`entity_id`, `is_read`, `read_at`, indexed by `(recipient, created_at)` and `(recipient, is_read)`.
- Service `NotificationService.send/query/mark_read/mark_all_read` (`service.py`). `send()` writes in-app + **optional email** via Celery `send_email` when `EMAIL_NOTIFICATIONS_ENABLED` and a recipient email exists (`service.py:61-62, 138-154`) — email plumbing already exists, just gated off.
- Router (`router.py`): `GET /` (paged, `unread_count` included), `PATCH /{id}/read`, `POST /read-all`. All tenant roles allowed.
- **Frontend bell exists**: `NotificationsDrawer.tsx` (slide-over, unread badge, mark-all-read, 60s poll) and a `notifications-count` query key for the bell counter.

**Event coverage today** (where `NotificationService.send` is actually called):

| Emitted today | Source |
|---|---|
| Course assigned / revoked | `m_academics/assignment_service.py:337,414` |
| Enrollment created/moved/unenrolled, USN/admission-year assigned | `m11_sis/enrollment_service.py` |
| Attendance shortage warning | `m11_sis/attendance_service.py` |
| Internal marks published | `m11_sis/marks_service.py` |
| Syllabus rejected / revision requested / approved / version created | `m02_syllabus/router.py` |
| Learning package curated | `workers/heavy/curate_learning_package.py` |

Enum `NotificationType` (`models.py:10-37`) already defines these. The column is a plain `String`, so **new types need no migration.**

### Problems

- **Coverage is patchy and role-blind.** No notifications for: Course Kit approved/rejected, new Course Kit available, assignment published/graded (student), PPT/Notes/Resources uploaded, hall ticket available, result published, dean-submitted-for-board, board evaluation pending. The requested matrix in the brief is ~70% unmet.
- **No notification center / history page** — only a 20-item drawer. No filtering, no "all notifications" route, no per-type grouping.
- **No preferences** — recipients cannot mute categories; email is a global flag, not per-user/per-type.
- **No fan-out helper** — every call site hand-builds title/body and recipient. There's no "notify all students in section X" or "notify dean of program Y" utility, so broadcasting is why the coverage is thin.
- **Delivery is best-effort, not guaranteed** — `send()` commits the in-app row then fires email fire-and-forget; no outbox, no retry ledger for the in-app row itself (fine for MVP, note for scale).

### Recommended enterprise notification architecture

**Layered design:**

1. **Event layer** — a small `notify.py` dispatcher with typed helpers:
   `notify_user(...)`, `notify_role_in_program(...)`, `notify_section_students(...)`, `notify_program_dean(...)`. Every domain event calls one helper; recipient resolution lives in one place.
2. **Category + preference layer** — group `NotificationType` into categories (Academic, Approvals, Attendance, Results, Materials, Governance). Add `notification_preferences(user_id, category, in_app, email)` for opt-out. Default all-on.
3. **Channel layer** — in-app (exists) + email (exists, gate on) + future push. `send()` already models this; add a `channel` fan-out driven by preferences. Keep an **outbox row** per channel for retry/audit (append-only, aligns with audit rules).
4. **Surfaces** — keep the bell + unread counter; add a full **Notification Center** page (`/notifications`) with tabs by category, read/unread filter, infinite scroll, and deep-links via `entity_type`/`entity_id` (already stored, currently unused for routing).

**Full event matrix to implement (phased):**

- *Faculty*: assignment approved/rejected, syllabus approved/rejected, course-kit approved/rejected, new course assigned (✔ exists), program assignment changed, dean comments, attendance reminder, internal-mark reminder.
- *Dean*: faculty submitted syllabus (✔ via syllabus events), faculty submitted course-kit, approval requests, pending-approval digest, faculty assignment updates.
- *Board*: dean submitted for approval, evaluation pending, final approval required.
- *Admin*: governance updates, new dean, faculty updates, system events.
- *Student*: assignment published/due/graded, marks published (✔ internal marks), attendance shortage (✔), material uploaded (PPT/Notes/Resources), new course kit available, hall ticket available, result published.

**Priority**: bell + center + email-on already exist → **P1 = broaden coverage via the dispatcher** (highest value, lowest risk). P2 = preferences. P3 = push + outbox.

---

# MODULE 4 — Attendance

### Current State (stronger than the brief assumes)

The backend is already close to ERP-grade. `m11_sis/attendance_*`:
- **Present/Absent only** — exactly the requested model (`attendance_models.py:38-41`, `AttendanceStatus`).
- **Sessions** per course+section+date+period, unique-constrained (`attendance_models.py:45-56`); lifecycle OPEN→LOCKED with a 48h edit window anchored on first mark; ADMIN/DEAN reopen with reason (`attendance_router.py:208-225`). Full audit trail on records (`marked_by/at`, `edited_by/at`, `edit_reason`).
- **Faculty**: create session, mark (bulk in one payload), edit record, per-course shortage report (`/attendance/shortage/my-courses`).
- **Analytics (ADMIN/DEAN)**: dashboard, shortage report with program/batch/section/course filters, **grouped** shortage, section analytics (`attendance_router.py:232-337`).
- **Student self-view**: `/attendance/me` summary and `/attendance/me/course/{id}` detail with threshold (`attendance_router.py:344-375`).
- **Frontend**: `AttendanceMarkPage`, `AttendanceSummaryPage`, `AttendanceAnalyticsPage`, `FacultyShortageReportPage` exist.

So of the brief's wish-list, **most already exists on the backend.** The real gaps are UX assembly and a few data views.

### Problems / gaps vs. the requested faculty screen

- **No single "Today's Class" faculty cockpit** — marking, roster, and summary are separate pages rather than one screen with Course/Dept/Program/Sem/Section context + student list + Bulk Present/Absent + quick search.
- **Bulk Present/Absent**: the mark payload accepts many records at once, but there's no verified one-click "mark all present then toggle absentees" UX affordance surfaced.
- **Monthly graph / monthly attendance** for students: `/attendance/me` returns a summary; a month-bucketed series for a graph isn't a first-class response shape (needs a per-month aggregate).
- **Attendance reminder** notification (faculty forgot to mark) — not emitted.
- **Dean analytics** exist as reports but not as a **visual dashboard** (program-wise/faculty-wise/section-wise cards + low-attendance alerts) — the data endpoints are there; the dashboard page is thin.

### Recommendations (benchmarked to ERPNext Education / PeopleSoft Campus / PowerCampus)

1. **Faculty "Take Attendance" cockpit** (one screen): context header (Course · Dept · Program · Sem · Section · Date/Period) → student list defaulting to Present → search + Bulk Present/Bulk Absent → save → shows session summary + this-month % inline. Backed entirely by *existing* endpoints.
2. **Student attendance page** with % ring, history table, and a **monthly bar graph** — add one aggregate endpoint returning `[{month, present, total, pct}]`.
3. **Dean attendance dashboard** — surface the existing grouped shortage + dashboard endpoints as cards: program-wise, faculty-wise, section-wise, and a Low-Attendance Alerts list at the configured threshold.
4. **Attendance reminder** — daily Celery job: for each faculty with a scheduled class and no OPEN/LOCKED session that day, emit `ATTENDANCE_REMINDER` (new type, no migration).
5. Keep the 48h lock + reopen governance (it's good ERP hygiene).

### Proposed Architecture

- Mostly **frontend assembly + one monthly-aggregate endpoint + one reminder worker.** No schema change to the attendance tables. Follows the dataviz skill for the charts.

---

# MODULE 5 — Board Governance

### Current State

- Board members surface today only as a **read-only tab** in `GovernanceDirectoryPage.tsx` (`BoardTab`/`BoardCard`) — avatar, name, designation, email, department. No profile drill-in, no committees, no approval history.
- BOARD is currently an **ADMIN-only responsibility grant** on a FACULTY login (`faculty_role_grants`, `docs/governance-model.md:26-31`), *not* a first-class entity.
- `docs/governance-model.md:46-57` already records the **approved future direction**: an external `board_members` registry decoupled from `users`, so external examiners / industry experts / university nominees can serve **without** a FACULTY login; internal faculty link via optional `user_id`. **This is explicitly deferred and must not be built without sign-off.**

### Problems

- A board member's card shows **faculty-flavoured fields** (department) and no governance context. There is no way to click through to a real board profile.
- No committees, no approval history, no activity timeline, no permissions view, no audit history surfaced — even though `audit_logs` already captures the underlying events.
- Modelling board membership as a faculty grant blocks the genuine use case (external, login-less members).

### Recommendations (align with the already-approved direction; build later)

Clicking a board member opens a **complete board profile** with:
- **Personal Information** — name, contact, external/internal source.
- **Governance Information** — role on board, term, appointing authority.
- **Assigned Committees** — from the future `board_members`/committee linkage.
- **Approval History** — query `audit_logs` filtered to this member's ratification events.
- **Activity Timeline** — chronological audit view.
- **Permissions** — what this board role may approve.
- **Status** & **Audit History** — active/inactive + append-only trail.
- **No faculty-specific actions** (no teaching load, no course kit) on this page.

Admin manages board members from this profile (create external member, assign committee, set term) — gated behind the future `board_members` table.

### Proposed Architecture

Adopt the deferred design verbatim: new tenant table `board_members` (+ committee linkage), optional `user_id` for internal faculty, `source ∈ {INTERNAL_FACULTY, EXTERNAL_EXAMINER, INDUSTRY_EXPERT, UNIVERSITY_NOMINEE, ACADEMIC_COUNCIL}`. Board profile page reads member + committees + `audit_logs` slice. **Requires sign-off per governance doc; not part of this analysis pass.**

---

# MODULE 6 — Course Kits (audit)

This module is covered exhaustively in `docs/course_kit_learning_package_reality_audit.md`. Summary of what that audit established, mapped to the brief's checklist:

### Current State

- **Lifecycle**: DRAFT → AI_GENERATING → PUBLISHED → ARCHIVED (`m03/models.py:14-18`). Create requires a DEAN-approved syllabus. **Single-actor publish — no dean sign-off gate on the kit itself.**
- **Slides**: fixed 10-type sequence, schema-validated, answer-key-leak scanned (`ai_provider.py`). **Quizlets** exist. **Assignments** (KitAssignment) full CRUD + rubric.
- **Teaching Plan**: generated + rendered to PPTX table. **Lesson Plans**: generated + stored but **not rendered in export**.
- **Compliance**: structural only (min slides/quizlets, non-empty teaching plan) — **no NBA/NAAC/CO-coverage logic** despite `co_reference` fields existing.
- **AI generation**: production-grade, async Celery, Gemini→Groq→DeepSeek fallback.
- **Version history**: `version` + `parent_version_id`, fork-to-new-draft.
- **Export**: real `python-pptx` PPTX + `reportlab` PDF/handout to S3, presigned URL, role-based field redaction.
- **Draft/Published/Archived**: all real DB states.

### What exists / no longer exists (brief's explicit questions)

- **Learning Packages**: still exist — the *most* complete module (m05), but have **zero connection** to Course Kit (separate data models).
- **Videos**: NOT IMPLEMENTED as files (YouTube-by-URL metadata only).
- **PDF resources**: only as *generated exports*; genuine PDF **upload** exists only via m05 faculty notes.
- **Research papers**: arXiv metadata only; no distinct papers entity.
- **External resources**: `PackageItem.url` bare-link mechanism in m05.

### Is the AI-generated PPT suitable for real university teaching?

Partially. The pipeline produces a structurally valid, per-slide-type PPTX with speaker notes and a teaching-plan table — usable as a *scaffold*. But: fixed 10-slide structure (not adjustable to a 40-min lecture vs a 3-hour unit), lesson plans not in the export, no faculty-authored slide upload, and no images/diagrams generation. It is a strong first draft, **not** a finished lecture deck.

### Problems

- No dean review/approve/reject on the kit (contrast: Syllabus module has full reject/resubmit).
- No faculty upload of their own PPT/PDF/notes *into the kit*.
- No student-facing surface for course kits at all (no role, no route).
- Course Kit list shows raw `syllabus_id` UUID instead of resolved course/program names.

### Recommendations (document only)

1. **Editable PPTX round-trip** — let faculty download the generated PPTX, edit in PowerPoint, and re-upload as the published artifact (reuse m05's proven storage + ingest pattern; additive endpoint + `course_kit` storage entity type which already exists but is dead).
2. **Faculty upload lane** inside the kit for Notes / PDF / PPT / Lab Manuals / Reference Material → these become kit resources.
3. **Auto-distribute to enrolled students** — a published kit's resources appear for students enrolled (via `acad_enrollments` → section → course). (Ties into Module 7.)
4. **Port the Syllabus dean reject/resubmit workflow** to Course Kit (state machine has room; add `PENDING_REVIEW` + dean action + `SUBMITTED`/`REJECTED` notifications).
5. **Resolve names on the list view** (frontend-only; data already fetchable).

---

# MODULE 7 — Faculty Upload Workflow (do uploads reach students?)

### Current State

- The **only** genuine faculty file-upload path is m05 **faculty notes**: `POST /learning-packages/{package_id}/notes` (`m05/router.py:306-359`) — PDF/TXT/DOCX, text-extracted, best-effort S3, fed to RAG, audit-logged.
- **Faculty-added link items**: `POST /{package_id}/items` (arXiv/YouTube/etc. metadata).
- Course Kit exports (PPTX/PDF) are *generated*, downloaded by faculty — not an upload.

### Problems — **uploads do NOT automatically reach students.**

- Learning-package **read RBAC includes STUDENT** (`_FULL` in `m05/router.py:71`), so a student *can* fetch a package and its items **if they know the package_id** — but there is **no student-facing "my materials" surface** that lists packages for the courses they're enrolled in. Discovery is missing.
- There is **no linkage from `acad_enrollments` (student→section→course) to learning packages** (packages FK to `syllabus_id`, not to a section/enrollment). So "students in that course automatically receive access" is **not** how it works today — access is possible but not *delivered* or *scoped by enrollment*.
- No notification when material is uploaded (Module 3 gap).

### Recommendations (document only)

**Enterprise workflow:** Faculty uploads material → material attaches to a *course* (not just a syllabus) → students **enrolled in that course's section** automatically see it in a **"Course Materials"** student page → student gets a `MATERIAL_UPLOADED` notification.

- Add a course/section linkage to uploaded materials (or resolve syllabus→course→sections→enrollments).
- Add a student **My Courses → Materials** surface (there is already `MyCoursesPage.tsx`; extend it).
- Emit notifications on upload/publish.
- Keep faculty upload using the existing m05 storage/ingest pattern (don't rebuild).

---

# MODULE 8 — Faculty Profile

### Current State

`frontend/src/pages/sis/FacultyProfilePage.tsx` (admin/dean view of a faculty) already renders a lot:
- Identity (faculty code, institution email, personal login), avatar, teaching programs.
- **Responsibilities card** with live grant management (ADMIN grants FACULTY/GUIDE/EVALUATOR; DEAN grants GUIDE/EVALUATOR) — `ResponsibilitiesCard`.
- Contact & basics, academic profile (qualifications/specialization/bio), department, **lifecycle panel** (ACTIVE/INACTIVE/ARCHIVED with human-ratified transitions + history), teaching programs, governing programs (dean), **active course assignments** with role chips.
- Backed by `FacultyDirectoryService.get_detail` (`directory_service.py`) → `FacultyDetailOut`.

So the profile is **already fairly complete** — the brief's list is ~60% present.

### Problems / missing sections

- **No teaching load metric** (course count / student count / weekly hours).
- **No attendance summary** for the faculty's sessions.
- **No pending reviews** (syllabus/course-kit awaiting their action).
- **No research interests** as a structured field (only free-text specialization/bio).
- **No activity timeline** (audit slice) and **no notifications** context.
- **No semesters/sections rollup** distinct from course assignments.

### Recommendations (document only) — target sections

Academic Identity (✔) · Programs (✔) · Courses (✔) · Semesters · Sections · **Research Interests** (structured) · **Teaching Load** (derived: courses × sections × students) · **Course Materials** (from Module 7) · **Attendance Summary** (from Module 4 faculty endpoints) · **Student Count** (from enrollments) · **Pending Reviews** (syllabus/kit queues) · **Notifications** · **Activity Timeline** (audit_logs slice).

Most are **derivable from existing endpoints** — this is largely a read-aggregation + layout task, not new schema.

---

# MODULE 9 — Platform-wide Module Review

Concise per-module scorecard. Purpose / current workflow / strengths / weaknesses / missing / ERP best practice / priority.

| Module | Current state (files) | Strengths | Weaknesses / Missing | Priority |
|---|---|---|---|---|
| **Authentication** | `core/auth`, primary role + responsibility grants, first-login flow, admin login | Clean role/responsibility split; tenant-scoped | No SSO/SAML; MFA unverified | P3 |
| **Platform Console / Tenants** | `core/tenants`, `pages/admin/Tenant*`, migrations runner, provisioner | Real multi-tenant schema isolation, per-tenant migrations, branding | Tenant-level analytics thin | P3 |
| **SIS** | `m11_sis/*` (huge: directory, enrollment, marks, exams, results, transcript, hallticket, graduation, rollover) | Deep, production-grade; most complete area | Sprawling; many peer pages; discoverability | P2 |
| **Students** | directory + self-service profile | USN allocation, lifecycle | Student portal fragmented across pages | P2 |
| **Faculty** | directory, profile, responsibilities | Rich profile, lifecycle, grants | See Modules 1/8 | P1 |
| **Departments/Programs/Semesters/Sections** | `pages/academics/*`, `acad_*` tables | Correct hierarchy | Program→dept moves leave stale denorm (Mod 1) | P2 |
| **Attendance** | Module 4 | Backend ERP-grade | UX assembly, monthly graph, reminders | P1 |
| **Internal Marks** | `m11_sis/marks_*` | Setup→entry→report→publish, notifications | Human-ratification depth unverified | P2 |
| **Examinations** | `m08`, `m09`, digital exams, seat alloc, invigilation, centers | Broad exam lifecycle | Legacy AI lineage (no DeepSeek), OCR review | P2 |
| **OCR** | `pages/OCRReview*` | Review queue exists | Accuracy/throughput unknown | P3 |
| **Research** | `m07_research_supervision`, viva | Viva engine, ratify | Legacy AI lineage | P3 |
| **AI Evaluation** | `m06_labs_evaluator`, evaluator dashboards | Double-evaluation, fairness report | AI advises only — verify no autonomous grading | P2 |
| **Course Kits** | Module 6 | AI gen + export real | No dean gate, no student surface | P1 |
| **Assignments** | `pages/assignments/*`, `m_academics` | Faculty create/manage | Student publish/grade notifications missing | P2 |
| **Notifications** | Module 3 | Bell + email plumbing | Coverage, center, prefs | P1 |
| **Governance** | ownership, dean scope, governance directory | Dean program scoping enforced | Board incomplete (Mod 5) | P1/P2 |
| **Analytics** | attendance, exam, bell-curve, digital | Several real dashboards | Not unified; no exec overview | P3 |
| **Results** | `m11_sis/results_*`, declarations, rank list | Declaration→verify→publish | Result-published notification missing | P2 |

**Cross-cutting strengths**: multi-tenant isolation, append-only audit log, async AI via Celery, real storage abstraction.
**Cross-cutting weaknesses**: notification coverage, "two ways to say the same thing" (Module 2), denormalisation drift (Module 1), student-facing surfaces are thin (Modules 6/7), legacy AI lineage in m06–m09.

---

# UI / UX Consistency Review

### Observed patterns

- **Two color systems coexist.** Some pages use semantic tokens (`text-foreground`, `text-muted-foreground`, `bg-white`, `border-gray-200`) — e.g. `FacultyProfilePage`, `FacultyResponsibilitiesPage`. Others hardcode hex + `slate-*` (`GovernanceDirectoryPage`: `#ec4899`, `text-slate-500`, `#7c3aed`). Chips define the *same* role colors independently in at least three files (`ROLE_COLORS`, `RESPONSIBILITY_COLORS`, `RESP_COLORS`).
- **Readability**: light theme with white cards + gray borders is clean where tokens are used. The brief flags "excessive blue glow / poor readability" — most audited pages are actually flat/clean; risk areas are any remaining dark/glow cards and low-contrast muted-on-white (`text-gray-400` on white for primary values).
- **Information visibility gaps**: Course Kit list shows raw UUIDs; Faculty Responsibilities buries responsibilities entirely; Board cards show faculty-shaped fields.

### Recommendations

1. **Single design token source** — centralise role/status/responsibility colors in one module (`lib/theme` or Tailwind config) and delete the per-file color maps. One `RoleChip`, one `StatusBadge`, one `ResponsibilityChip` shared component.
2. **Contrast pass** — primary values use `text-foreground`/`text-gray-900`, never `text-gray-400`; muted only for labels.
3. **Kill raw IDs** — always resolve to human names (course/program/semester), matching the Syllabus list treatment.
4. **Consistent page shell** — every page through `PageShell`/`PageHeader` (most already do).
5. Use the **dataviz skill** palette for all charts (attendance, analytics) so light/dark read as one system.

---

# Duplicate Feature Analysis

| Apparent duplication | Verdict | Detail |
|---|---|---|
| Ownership Matrix vs Course Assignments | **Same data, two views** | Matrix is a read-only projection of `subject_assignments` (`ownership_service.py:743-826`). Keep both; reframe Matrix as coverage analytics, not data entry. |
| Faculty Programs vs Course Assignments | **Partial overlap** | Program membership is implied by course teaching already; `faculty_program_assignments` uniquely adds coordinator (`is_primary`) + pre-course membership. Narrow Faculty Programs to those. |
| `get_faculty_responsibilities` array counts vs `get_faculty_summary` UNION counts | **Redundant counters** | Two code paths compute the same stats; collapse to one. |
| `/me/responsibilities` (role grants) vs Responsibilities page (teaching) | **Name collision, not data dup** | Two meanings of "responsibilities"; merge into one aggregate view. |
| Notification color maps (×3), role color maps (×3) | **True duplication** | Consolidate to shared components/tokens. |
| Course Kit export PPTX vs faculty PPT upload | **Not dup** | One is generated, the other (proposed) is uploaded; complementary. |
| Learning Package vs Course Kit | **Not dup, disconnected** | Separate data models, no link; a bridge is an enhancement, not a merge. |

---

# Prioritized Enterprise Redesign Roadmap

Ordering respects dependencies. Complexity: **S** ≤ ~2 days, **M** ~1 week, **L** multi-week. **No implementation now — each item enters its own Plan → Approval → Implement → Commit → Manual-test cycle.**

### Wave 1 — Correctness & trust (do first)

1. **Fix Faculty Responsibilities data model (Module 1).**
   - *Dependency*: none. *Complexity*: **M**.
   - *Backend*: `m_academics/ownership_service.py` (responsibilities/summary queries), `m11_sis/directory_service.py` (home dept), merge `/me/responsibilities`.
   - *Frontend*: `pages/faculty/FacultyResponsibilitiesPage.tsx`, `hooks/useOwnership.ts`, `lib/api/ownership.ts`.
   - *DB*: none required; optional reconciliation job for stale `faculty_program_assignments.department_id`.

2. **Broaden notification coverage via a dispatcher (Module 3, P1).**
   - *Dependency*: none (infra exists). *Complexity*: **M**.
   - *Backend*: new `core/notifications/dispatch.py`; call sites in `m03_course_kit/service.py`, `m_academics/assignment_service.py`, `m11_sis/results_service.py`, `marks_service.py`, `m02_syllabus`, `m05` upload. Add enum values (no migration — string column).
   - *Frontend*: new Notification Center page + route; reuse `NotificationsDrawer`.
   - *DB*: none for types; **later** `notification_preferences` table (Wave 3).

3. **Disambiguate Dean governance pages (Module 2).**
   - *Dependency*: #1 (shared responsibilities model). *Complexity*: **S–M**.
   - *Backend*: add coverage/gap query in `ownership_service.py`; `source` discriminator in read model.
   - *Frontend*: reframe `DeanOwnershipMatrixPage` → coverage; narrow `DeanAssignFacultyProgramPage` to coordinators; nav rename.
   - *DB*: none.

### Wave 2 — Faculty & student experience

4. **Attendance UX assembly (Module 4).**
   - *Dependency*: #2 (reminders). *Complexity*: **M**.
   - *Backend*: one monthly-aggregate endpoint + reminder Celery worker (`m11_sis/attendance_service.py`, `workers/`).
   - *Frontend*: faculty cockpit (`AttendanceMarkPage`), student monthly graph (`AttendanceSummaryPage`), dean dashboard (`AttendanceAnalyticsPage`). Use dataviz skill.
   - *DB*: none.

5. **Faculty upload → student delivery (Modules 6 & 7).**
   - *Dependency*: #2. *Complexity*: **L**.
   - *Backend*: link uploaded materials to course/section (resolve `syllabus→course→sections→enrollments`); reuse m05 storage/ingest; `MATERIAL_UPLOADED` notify.
   - *Frontend*: student **My Courses → Materials** (`pages/MyCoursesPage.tsx`); faculty upload lane in course kit / learning package.
   - *DB*: possibly a `material ⇄ course/section` link (small additive table) or pure query resolution.

6. **Faculty Profile completion (Module 8).**
   - *Dependency*: #4 (attendance summary), #5 (materials). *Complexity*: **M**.
   - *Backend*: aggregate teaching load / student count / pending reviews / activity slice in `directory_service.py`.
   - *Frontend*: `pages/sis/FacultyProfilePage.tsx` new sections.
   - *DB*: optional structured `research_interests`.

### Wave 3 — Governance & polish

7. **Course Kit dean review + editable PPTX (Module 6).**
   - *Dependency*: #2. *Complexity*: **M** (review) / **M** (upload).
   - *Backend*: `m03_course_kit` add `PENDING_REVIEW` + dean action (port Syllabus pattern); `course_kit` storage entity type (exists, dead) for uploads.
   - *Frontend*: dean review UI + faculty upload; resolve names on `CourseKitListPage`.
   - *DB*: additive status value / review columns (migration).

8. **Notification preferences + email-on + push (Module 3, P2/P3).**
   - *Dependency*: #2. *Complexity*: **M**.
   - *DB*: `notification_preferences` table (migration); optional outbox table (append-only).

9. **Board governance registry (Module 5).**
   - *Dependency*: **explicit sign-off** (governance doc marks it deferred). *Complexity*: **L**.
   - *Backend*: new `board_members` (+ committees) tenant tables; board profile read (member + committees + `audit_logs`).
   - *Frontend*: board profile page; admin management.
   - *DB*: new tables + migration.

10. **UI token/component consolidation + contrast pass (UI/UX).**
    - *Dependency*: none (can run parallel). *Complexity*: **S–M**.
    - *Frontend*: shared `RoleChip`/`StatusBadge`/`ResponsibilityChip`, central color tokens, remove per-file hex maps; contrast fixes.
    - *DB*: none.

### Dependency summary

```
#1 Faculty Responsibilities ─┬─> #3 Dean pages ─> #7 Course Kit review
                             └─> #6 Faculty Profile
#2 Notification dispatcher ──┬─> #4 Attendance UX ─> #6
                             ├─> #5 Uploads→students ─> #6
                             ├─> #7
                             └─> #8 Preferences/push
#9 Board registry (needs sign-off, independent)
#10 UI consolidation (independent, parallel)
```

---

## Reminder for all future work

1. Produce a detailed implementation plan.
2. Wait for approval.
3. Implement only the approved scope.
4. Commit with a proper message.
5. **No automated tests, no test runs** — the team performs manual testing after each phase.
