# Exam Module — Manual Testing Kit (Task 1)

> Purpose: verify the completed Exam Paper business workflow end-to-end on a fresh
> tenant. **You execute this manually.** For every failure, report the step number
> + what you saw; I will diagnose, fix, and ask you to retest. Nothing here is
> auto-verified by me — do not assume a step passes until you see the expected result.

---

## 0. What changed in Task 1 (so you know what you are testing)

Backend (`backend/app/modules/m08_exam_setter/`):

- `service.py`
  - `_assert_can_finalize`: **INTERNAL finaliser is now the DEAN** (was Faculty). Board still finalises BOARD_EXAM.
  - `seal()`: **no automatic release is scheduled** anymore. `release_job_id` is left NULL; `release_at` is stored only as a *planned* date. Release is manual.
  - `create()`: **Faculty cannot create an END_SEM (Semester-End) paper** → 403. Board only.
  - `_DELETABLE_STATUSES`: now **DRAFT / GENERATED / BOARD_RETURNED** only (FAILED removed).
  - `faculty_approve()` **removed** — internal papers are approved by the Dean, not self-approved.
- `router.py`
  - `/seal` and `/release` are now gated to **DEAN / BOARD / ADMIN** (Faculty removed).
  - `/faculty-approve` endpoint **removed**.

Frontend:

- `lib/examStatus.ts`: `canDeletePaper` mirrors backend (no FAILED).
- `pages/ExamPaperEditorPage.tsx`: internal finaliser = Dean (`canFinalize`); seal modal reworded to "Lock", release is manual.
- `lib/api/exam.ts`: removed dead `facultyApprovePaper`.

Everything else (template engine, blueprint, AI generation, PDF, encryption/seal mechanism) is **unchanged**.

---

## 1. Prerequisites (do this first)

1. **Apply all tenant migrations to the latest HEAD revision before starting manual testing.**
   Do not stop at a specific revision — always migrate the tenant schema to HEAD (via
   Admin → Tenant Migrations, or `alembic upgrade head` for the tenant schema). These add,
   among others: `creation_mode`, `blueprint`, `template_definition`, `template_block_id`,
   `unit_numbers`, `difficulty`, assignment evaluator columns, the assignment `questions` /
   `question_paper_url` columns, and the calendar holiday seed.
   ▶ **Expected:** `alembic current` (tenant) matches the latest HEAD. No errors.
   ▶ **If any manual test fails because a database column is missing, first verify the tenant
   schema is migrated to HEAD before investigating application code.**
2. **Env:** set `EXAM_FERNET_KEY` to a valid 44-char Fernet key (otherwise sealed papers
   cannot be unsealed after a worker restart — dev-only ephemeral key is used).
   AI keys (`GEMINI_API_KEY` / `GROQ_API_KEY` / `DEEPSEEK_API_KEY`) are optional — without
   them, generation uses the syllabus-aware **mock** generator (paper is structurally valid
   but placeholder text; `ai_model = "mock"`).
3. **Services running:** Postgres, Redis, API (FastAPI), **Celery heavy worker** (required for
   AI generation), and the frontend.
   ▶ Without the Celery worker, AI paper creation returns 503 `QUEUE_UNAVAILABLE` — that is
   expected and is itself a test (Suite G-4).

---

## 2. Test data — "ABC University"

Create in this order (each depends on the previous):

| # | Entity | Details | Why needed |
|---|---|---|---|
| 2.1 | Tenant | Name: **ABC University** | root |
| 2.2 | Admin login | the tenant admin | provisions users |
| 2.3 | Program | e.g. **B.E. Computer Science** | courses hang off it |
| 2.4 | Department | e.g. **CSE** | |
| 2.5 | Course/Subject | e.g. **CS301 — Data Structures** | papers are per course |
| 2.6 | Users | 1 DEAN, 1 BOARD, 1 FACULTY, 1 EVALUATOR, 2 STUDENTS | each workflow role |
| 2.7 | Dean→Program assignment | Dean governs the CS program | Dean queue scoping |
| 2.8 | Faculty→Course assignment | Faculty teaches CS301 | `faculty_teaches_course` gate |
| 2.9 | **Syllabus for CS301** | ≥3 units with titles+topics, ≥2 COs, **status APPROVED/LOCKED** | **papers REQUIRE an approved syllabus** |

▶ **Validation point 2.9:** If the syllabus is not APPROVED/LOCKED, every paper-create
attempt must fail with `NO_APPROVED_SYLLABUS` (409). Confirm this before proceeding.

---

## 3. Suite A — Internal Assessment (happy path)

Actor changes are called out per step. Use the **workspace switcher** to act as the right role.

| Step | Actor | Action | Expected result |
|---|---|---|---|
| A1 | Faculty | Create paper: course CS301, **exam_type = INTERNAL**, **workflow = INTERNAL**, creation_mode = AI, pick units, set blueprint/template, Bloom's summing to 100 | 202 accepted; paper appears with status **Generating**, then **Generated** (poll). Job id returned. |
| A2 | Faculty | Open the paper in the editor | Questions listed. Buttons visible: **Submit**, **Delete**, **Download PDF**, **Regenerate**, **Edit**. No Lock/Release. |
| A3 | Faculty | Click **Download PDF** (status GENERATED) | A print-ready PDF downloads. Header, sections, marks present. No model answers. |
| A4 | Faculty | Edit a question / regenerate one question | Edit saves (`is_edited` true). Regenerate returns 202; question updates after the job runs. |
| A5 | Faculty | Click **Submit** | Status → **Submitted to Dean**. **Delete button disappears. Edit/Add/Reorder disappear.** Paper is read-only for Faculty. |
| A6 | Dean | Go to `/exams/dean/pending` | The paper appears in the Dean's pending queue (department-scoped). |
| A7 | Dean | Click **Approve** | Status → **Dean Approved** (BOARD_APPROVED). |
| A8 | Dean | Open the paper in the editor (`/exams/:id`) | **Lock** button visible (Dean is the finaliser). No Submit/Delete. |
| A9 | Dean | Click **Lock**, set a planned release date/time (future), confirm | Status → **Sealed**. Modal states release is manual. |
| A10 | Dean | (still on the paper) Click **Release Now** | Status → **Released**. `released_at` set. |
| A11 | Anyone (read) | Open the paper / export PDF | PDF export works (RELEASED). Questions readable. |

▶ **Validation points:**
- After A5 the paper must be **uneditable and undeletable** by Faculty (see Suite E/H).
- At A9 the paper is **encrypted**; questions endpoint returns 403 `SEALED_ACCESS` while SEALED.
- Between A9 and A10 **no automatic release occurs** even after the planned time passes — release only happens when the Dean clicks Release (this is the core Task-1 change; wait past the planned time to confirm it stays SEALED until A10).

---

## 4. Suite B — Internal return / resubmit cycle

| Step | Actor | Action | Expected |
|---|---|---|---|
| B1 | Faculty | Create + Submit an INTERNAL paper (as A1–A5) | Status **Submitted to Dean**. |
| B2 | Dean | In pending queue, click **Return**, enter a comment (required) | Status → **Dean Returned** (BOARD_RETURNED). Comment stored. |
| B3 | Faculty | Open paper | Editable again. Edit/Add/Delete/**Submit** visible. Dean's comment shown. |
| B4 | Faculty | Edit, then **Submit** again | Status → **Submitted to Dean** again. |
| B5 | Dean | Approve → Lock → Release | Reaches **Released** as in Suite A. |

▶ **Validation:** Return **requires** a comment — returning with an empty comment must be rejected.

---

## 5. Suite C — Board Exam workflow

| Step | Actor | Action | Expected |
|---|---|---|---|
| C1 | Faculty | Create paper: **workflow = BOARD_EXAM**, exam_type = **not** END_SEM (e.g. CUSTOM/MID_SEM) | Status Generated. |
| C2 | Faculty | Submit | Status **Submitted** → goes to **Board** queue (not Dean). |
| C3 | Dean | Check `/exams/dean/pending` | Paper is **NOT** there (board papers are invisible to the Dean). |
| C4 | Board | Open Board review (`/exams/board/pending` / BoardReviewPage) | Paper listed. Can view questions **with model answers**. |
| C5 | Board | Return with comment | Status **Board Returned**; Faculty edits & resubmits (as Suite B). |
| C6 | Board | Approve | Status **Board Approved**. Questions **promoted to question bank** (is_approved). |
| C7 | Board | Lock (seal) | Status **Sealed**. |
| C8 | Board | Release | Status **Released**. |

▶ **Validation:** In C4, Faculty/Dean must **not** be able to see model answers; only BOARD/ADMIN via `/questions/with-answers`.

---

## 6. Suite D — Semester-End creation restriction

| Step | Actor | Action | Expected |
|---|---|---|---|
| D1 | Faculty | Try to create a paper with **exam_type = END_SEM** | **403 FORBIDDEN** — "Semester-End papers are created by the Board only." Paper NOT created. |
| D2 | Board | Create a paper with **exam_type = END_SEM** | Succeeds. Board owns it. |
| D3 | Board | Approve directly from GENERATED ("publish directly") | Allowed (board-owned paper). |

---

## 7. Suite E — Draft deletion rules

| Step | Actor | Paper status | Delete allowed? |
|---|---|---|---|
| E1 | Faculty | **DRAFT** / **GENERATED** | ✅ Delete works; paper + questions removed. |
| E2 | Faculty | **BOARD_RETURNED** | ✅ Delete works. |
| E3 | Faculty | **SUBMITTED** | ❌ No Delete button; API returns **409 INVALID_STATUS**. |
| E4 | Faculty | **BOARD_APPROVED / SEALED / RELEASED** | ❌ Delete blocked (409). |
| E5 | Faculty | **FAILED** | ❌ Delete blocked (see Known Issue K1 — flag if you want this changed). |
| E6 | Faculty | Delete a paper owned by **another** faculty | ❌ **403 FORBIDDEN**. |

---

## 8. Suite F — Manual paper creation

| Step | Actor | Action | Expected |
|---|---|---|---|
| F1 | Faculty | Create paper with **creation_mode = MANUAL** | No Celery job (job_id null). Status lands directly on **Generated** (empty). |
| F2 | Faculty | Add hand-written questions (respect template blocks if templated) | Questions saved with `ai_generated=false`. On a templated paper, a question with no `template_block_id` is rejected (`TEMPLATE_BLOCK_REQUIRED`). |
| F3 | Faculty | Reorder (drag), duplicate a question | Order persists; duplicate inserted right after its source. |
| F4 | Faculty | Download PDF, then Submit → (Dean) Approve → Lock → Release | Full workflow works identically to AI papers. |

---

## 9. Suite G — AI generation & PDF details

| Step | Actor | Action | Expected |
|---|---|---|---|
| G1 | Faculty | Create AI paper **with** LLM keys set | Real questions generated; `ai_model` = gemini/groq/deepseek. Bloom's compliance report present. |
| G2 | Faculty | Create AI paper **without** LLM keys | Mock generation; `ai_model = "mock"`; structurally valid placeholder questions. |
| G3 | Faculty | Check Bloom's / CO / unit coverage report on the paper | Advisory report displayed (compliance %, per-CO, per-unit). |
| G4 | Faculty | Create AI paper with **Celery worker stopped** | **503 QUEUE_UNAVAILABLE**; paper marked FAILED with reason. |
| G5 | Any | Export PDF at GENERATED and at RELEASED | PDF downloads at both. Sealed paper (between Lock and Release) → **403** on PDF export. |

---

## 10. Negative / permission checks (Suite H — do these deliberately)

| # | Actor | Attempt | Expected |
|---|---|---|---|
| H1 | Faculty | Call `/exams/{id}/seal` (any way) | **403** — "Only the Dean can lock or release an internal assessment paper" (INTERNAL) / Board (BOARD_EXAM). |
| H2 | Faculty | Call `/exams/{id}/release` | **403** (same rule). |
| H3 | Faculty | Edit a question after **Submit** | **400 INVALID_STATUS** (not editable). |
| H4 | Dean (other dept) | Approve/return a paper outside their program | **403 NOT_IN_SCOPE**. |
| H5 | Faculty | Old `/exams/{id}/faculty-approve` endpoint | **404** (endpoint removed). |
| H6 | Dean | Lock a paper that is not BOARD_APPROVED | **400 INVALID_STATUS**. |
| H7 | Faculty | Submit a paper with **zero** questions | **NO_QUESTIONS** error. |

---

## 11. Known issues / decisions to confirm (not bugs — your call)

- **K1 — FAILED papers are not deletable.** Your spec listed only Draft/Generated/Returned, so
  I removed FAILED from the deletable set. Consequence: a paper whose generation failed can only
  be retried, not deleted. If you'd rather Faculty be able to delete FAILED papers, say so and
  I'll re-add it.
- **K2 — Dean department-scope is enforced on approve/return but NOT on lock/release.** A Dean
  from another department could, in theory, Lock/Release an already-approved internal paper via
  the editor. Low risk (the paper was approved by the correct Dean first). Tell me if you want
  scope enforced on seal/release too.
- **K3 — `release_at` is now advisory only.** It is stored as a "planned release date" but nothing
  acts on it (no auto-release). Confirm the UI copy ("Planned Release Date") reads correctly to you.
- **K4 — `/export/questions` and `/export/answers` return JSON, not PDF** (pre-existing). Only
  `/export/pdf` returns a real PDF. Out of Task-1 scope; flagging for awareness.
- **K5 — Ephemeral Fernet key** if `EXAM_FERNET_KEY` unset: sealed papers can't be unsealed after
  a worker restart. Set the key before testing seal/release across restarts.

---

## 12. NOT YET IMPLEMENTED (so this kit does not pretend otherwise)

- **Task 2 — Course Kit AI PPT generation** is **not done yet**. The presentation engine in
  `backend/app/modules/m03_course_kit/presentation/` is the in-progress code to be completed
  next (download / edit-externally / re-upload / delete / regenerate / replace). Do **not** test
  the Course Kit PPT checklist items until Task 2 is implemented — I will extend this kit then.
- The broader checklist areas you listed (**Assignments/evaluator, Research, Analytics**) were not
  changed by Task 1. They can be smoke-tested, but any failure there is pre-existing, not from this
  sprint.

---

## 13. Reporting back

For each failed step, tell me: **step id** (e.g. A9), the **role** you were acting as, what you
**expected**, what **actually** happened (message / status / screenshot). I will diagnose the root
cause, fix it, and ask you to retest that step. We iterate until every suite is green — only then do
I write the final testing report.
