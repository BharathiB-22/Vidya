# Phase A V2 — University-Style Curriculum Governance

**Status:** IMPLEMENTED and verified end-to-end. **Nothing committed** — awaiting your sign-off.

**Verification**

- `python scripts/verify_governance_v2.py` — drives the entire workflow over HTTP against the real
  database as all five roles and asserts every gate: **49/49 checks pass**. Includes the Dean's
  pre-submission checklist, the Board's no-separation-of-duties rule (the same member who modified the
  curriculum approves it), and the governance trail (who reviewed / modified / approved, each named
  and timestamped).
- Backend suite (m01 + m02 + governance): **279 passed, 5 failed** — all 5 pre-existing and unrelated
  (3 × m01 program-structure AI-provider fallback, `test_dean_can_read_syllabus_list`, and
  `test_worker_event_loop`, which complains about a line `git diff` shows this work never touched).
  Before the fixture fix in §8b.3 the same run was 24 failed.
- Frontend: `tsc --noEmit` clean; `npm run build` succeeds.
- Migrations `0084ten` and `0085ten` applied to a real tenant schema (`tenant_vbs_university`) and
  the resulting columns/indexes verified.
- The official syllabus PDF was rendered from real data and its text extracted — it prints as a
  regulation page (Course Information table, Objectives, CO1–CO5 with Bloom levels, CO-PO matrix,
  Unit I–V as justified prose with hour allocations, TOTAL: 60 HOURS, Internal Assessment, and the
  four bibliography sections).

**Branch:** `feature/erp-onboarding`
**Supersedes:** `docs/phase-a-academic-governance.md` (V1, uncommitted in the working tree)

---

## 0. The model

The Dean is the **academic planner**. The Board is the **academic owner**. Faculty are **academic
executors**. Students are recipients.

The Board does not reject, return, or send work back — there is no path back. When the Board finds
the curriculum wanting, it **academically enhances** it: rearranging semesters, improving subject
flow and sequencing, adjusting credits, adding or removing electives. These are improvements to the
Dean's plan, made by the body that owns academic quality. The Dean is then told exactly what changed.

```
Dean creates Program Structure          ← existing flow, UNCHANGED
        │
        ▼
   Submit to Board                      ← governance begins HERE, and only here
        │
        ▼
   Board reviews Program
   Board edits Program Structure
   Board generates Official Syllabus    ← structure marked final automatically, no button
   Board reviews / edits Official Syllabus
   Board approves Curriculum            ← blocked until EVERY subject has an approved syllabus
        │
        ▼
   CURRICULUM LOCKED  (structure + syllabus, permanently)
        │
        ▼
   Dean notified: "Board has reviewed and finalized your curriculum."
   Dean reviews the change summary
   Dean publishes                       ← the Dean's only remaining action on this version
        │
        ▼
   Dean assigns faculty ──► Faculty build lesson plans, PPTs, course kits,
                            assignments, question papers, internal marks, attendance
                                    │
                                    ▼
                                Students
```

Three artifacts, three owners, no overlap:

| Level | Artifact | Owner | Anyone else? |
|---|---|---|---|
| 1 | **Program structure** — credits, semesters, core courses, elective baskets | Dean designs | Board enhances after submit |
| 2 | **Official subject syllabus** — objectives, COs, Unit I–V, books | Board generates, edits, approves | **Never** |
| 3 | **Teaching resources** — lesson plan, PPT, notes, course kit, assignments, question papers | Faculty create | — |

---

## 1. What does NOT change

Stated first, because it is the largest part of the system.

- **The Dean's program creation flow is untouched.** Program, semesters, credits, core courses and
  elective baskets are created exactly as they are today. Same models, same endpoints, same UI, same
  forms. **No redesign.**
- Governance begins at **Submit to Board** and nowhere earlier.
- **No new fields for the Dean to fill in.** Category and Contact Hours are *derived* (§2.2) — the
  Dean's course form does not gain a single input.
- **Existing published curricula are grandfathered.** No existing data is modified or invalidated.
  The new workflow applies only to curriculum versions created from now on.
- Untouched entirely: timetable, attendance, internal marks, course kits, learning materials,
  notifications infrastructure, student dashboard, role switching, faculty workspace switching,
  Academic Ownership, tenant architecture.

---

## 2. Database changes

One tenant migration: `0084ten_governance_v2.py` (head is `0083ten`). No new public migration —
`tenants.governance_type` already exists (`0017pub`).

### 2.1 `programs`

```sql
ALTER TABLE programs
  ADD COLUMN academic_year                 VARCHAR(9),    -- '2026-2028'
  ADD COLUMN structure_finalized_at        TIMESTAMPTZ,
  ADD COLUMN structure_finalized_by_user_id UUID;

CREATE UNIQUE INDEX uq_programs_curriculum_version
  ON programs (acad_program_id, effective_from_batch_id, version)
  WHERE acad_program_id IS NOT NULL AND effective_from_batch_id IS NOT NULL;
```

`structure_finalized_at` is set **automatically when syllabus generation first begins** — there is no
"Finalize Structure" button and no user-facing step. It is an internal record of the structure the
syllabus was generated against.

The Board may **freely edit the structure right up to approval**. There is no mid-flight freeze and
no reopen workflow. Instead, the **approve gate is the single invariant**:

- Edit a course whose syllabus is already `APPROVED` → that syllabus reverts to `DRAFT`, so the Board
  must re-review it before approving. A stale syllabus can never be locked.
- Add a course → it has no syllabus → the gate blocks approval.
- Delete a course → its syllabus cascades away.

Every path routes through one rule, so no additional state is needed. **Approval is the only freeze**,
and it is permanent: after it, structure and syllabus are both immutable, and any future academic
change is a new curriculum version created by the Dean.

A curriculum version **is** a `programs` row: `(acad_program_id, academic_year,
effective_from_batch_id, version)`. `effective_from_batch_id` already exists from `0083ten`.

`ProgramStatus.RETURNED` is deleted; existing rows migrate `RETURNED → DRAFT`. Final lifecycle:

```
DRAFT ──► PENDING_APPROVAL ──► APPROVED (locked) ──► PUBLISHED
  ▲                                                      │
  └───────────── new version (fork) ◄───────────────────┘
```

### 2.2 `courses` — NO CHANGES

Category and Contact Hours are **derived at read time**. The Dean enters nothing new.

**Category** — `Core · Elective · Lab · Project`, from fields that already exist:

```
is_elective = true          → Elective
course_type = LAB           → Lab
course_type = PROJECT       → Project
otherwise                   → Core
```

**Contact Hours** — from the existing L-T-P (`hours_lecture` / `hours_tutorial` /
`hours_practical`): `(L + T + P) × 15` weeks. Displayed on the syllabus; never entered.

Both are computed in one place (`m02/formatting.py`) and rendered into the syllabus header, so they
cannot drift from the curriculum.

### 2.2b The official syllabus content — migration `0085ten`

The AI was writing an **outline**. A university syllabus is a **document**. The unit model could only
hold a list of topic objects, so a generated unit came out as a couple of bullets — which is not what
a Board of Studies publishes.

```sql
ALTER TABLE syllabus_units ADD COLUMN content TEXT;               -- the prose block that PRINTS
ALTER TABLE syllabi        ADD COLUMN internal_assessment JSONB;  -- CIE suggestions
```

A unit now prints as a regulation does:

```
UNIT I - INTRODUCTION TO COMPUTER SYSTEMS                              (12 Hours)
Introduction to Computer Systems, Evolution of Computing, Von Neumann Architecture,
Instruction Cycle, Processor Organization, Memory Hierarchy, Cache Memory,
Input/Output Organization, Performance Metrics, Amdahl's Law, Benchmarking.
```

`topics` is **kept alongside** `content`, not replaced by it. The two serve different readers:
`content` is what a human sees in the published syllabus, while `topics` is what the course-kit
generator reads to plan lessons (`workers/heavy/course_kit_generation.py` builds its `unit_topics`
from it). Collapsing them into prose would silently degrade every course kit generated afterwards.

`RefType` gains `WEB_RESOURCE`, so the bibliography prints as **four** sections: Text Books,
Reference Books, Suggested Reading, Web Resources.

**A unit IS its topic list.** An AICTE / Anna University / VTU unit runs to **12–20** specific,
teachable topics, and that list is what a lecturer reads to know what to teach. So the topics are what
prints, what the Board edits, and where the depth guarantee lives. `content` (the comma-separated
prose rendering) is derived from the same topics, so a regulation that prints paragraphs and one that
prints bullets can never disagree.

**A thin unit is rejected, not published.** Enforced as *hard* errors that abort generation:

| Guard | Why |
|---|---|
| Fewer than 12 topics | Below that it is an outline, and the Board would have to write the rest by hand — the exact work the AI is there to do |
| Filler topics (`Introduction`, `Basics`, `Overview`, `Advanced Topics`, `Recent Trends`…) | *Looks* finished; a reader cannot tell what will be taught in the room |
| Repeated topics | A model that runs out of ideas pads. Fourteen lines that are really seven is the same hollowness in a longer coat |
| Not exactly 5 units | The format is Unit I to Unit V |
| Lab work on a theory course | A commitment the department can neither staff nor timetable |

Filler is matched on the **exact** normalised title, never as a substring: `Applications` alone says
nothing, while `Applications of Convolutional Networks` is a real topic, and a substring test would
throw the second away with the first.

**Per-section regeneration.** The Board can rewrite **one unit**, the **objectives**, the **outcomes**
or the **bibliography** on its own (`POST /syllabi/{id}/regenerate`), with optional guidance ("go
deeper on cache coherence; this overlaps Unit IV"). Nobody should have to regenerate a whole syllabus
because one unit came out weak — by then the other four and the outcomes will usually have been
hand-edited, and a full regeneration throws all of that away.

A regenerated unit is told **what the other units already teach**, so it fills its own place rather
than drifting into theirs — a unit rewritten in isolation is how you end up with two of them teaching
cache memory. And it is held to *exactly* the same depth bar as a full generation, so "regenerate this
one unit" cannot become the back door through which a thin unit reaches the document.

Regenerating any part of an **approved** syllabus withdraws that approval: the sign-off meant "I have
read exactly this", and it is no longer that.

### 2.3 `syllabi`

```sql
ALTER TABLE syllabi
  ADD COLUMN objectives           JSONB NOT NULL DEFAULT '[]',   -- Course Objectives
  ADD COLUMN practical_components JSONB NOT NULL DEFAULT '[]';   -- if applicable

ALTER TABLE syllabi RENAME COLUMN dean_comment TO board_comment;
```

`SyllabusStatus` collapses from six values to four. The Board authors *and* approves, so a
submit/review handoff state is meaningless:

```
DRAFT ─► AI_GENERATING ─► DRAFT ─► APPROVED ─► LOCKED
```

| Old | New |
|---|---|
| `DRAFT`, `PENDING_REVIEW`, `REJECTED` | `DRAFT` |
| `DEAN_APPROVED` | `APPROVED` |
| `DEAN_LOCKED` | `LOCKED` |

`created_by_user_id` on legacy faculty-authored syllabi is left as-is — that is historical truth.
Edit rights transfer to the Board regardless.

### 2.4 `syllabus_references` — no schema change

`RefType` is `native_enum=False` (a VARCHAR), so adding a value is a code change only:

```
TEXTBOOK           → "Text Books"
REFERENCE, JOURNAL → "Reference Books"
SUGGESTED_READING  → "Suggested Reading"    (NEW)
ONLINE             → "Suggested Reading"
```

### 2.5 `elective_baskets`

```sql
ALTER TABLE elective_baskets
  ADD COLUMN locked_at         TIMESTAMPTZ,
  ADD COLUMN locked_by_user_id UUID;
```

Two axes that must not be conflated:

- **Composition** (which subjects Elective 1 offers) — frozen when the curriculum is approved.
  *No new electives after lock.* Every elective subject has its own official syllabus and is covered
  by the approve gate.
- **Registration lifecycle** (`ElectiveSlotStatus`: `DRAFT → PUBLISHED → OPEN → CLOSED`) —
  **unchanged**. The Dean still opens and closes student registration each year on a published
  curriculum.

### 2.6 No new tables

The `curriculum_modifications` table proposed in rev 1 is **dropped from the plan**. Board changes
are tracked in the **existing audit log**, which already records `actor_role`, `event_type`,
`target_entity`, `target_id`, a JSONB `metadata` blob and `created_at` — and is already append-only
by project rule.

The only work: stamp `program_id` into the `metadata` of the structural-write audit calls that don't
already carry it, so the summary can be assembled with one query:

```sql
SELECT event_type, actor_user_id, metadata, created_at
FROM public.audit_logs
WHERE tenant_id = :tenant
  AND metadata->>'program_id' = :program_id
  AND created_at >= :submitted_at          -- Board's tenure over this curriculum
  AND actor_role IN ('BOARD','ADMIN')
ORDER BY created_at;
```

`curriculum_approval_requests` (V1) is kept as-is. Historical `RETURNED` rows are **retained** — it
is an append-only ledger and deleting audit history would break the project's own rule. The
`RETURNED` *write path* is deleted from the code; `cycle` is always 1 going forward.

---

## 3. Backend services

### 3.1 `core/governance/service.py`

**Deleted:** `return_to_dean()` and every `RETURNED` code path.

**`submit_for_approval()`** — additionally requires `academic_year` + `effective_from_batch_id` (a
curriculum must know which batch it governs). Still compliance-gated. The Dean becomes permanently
read-only on this version.

**Structure edits stay open for the Board for the whole of `PENDING_APPROVAL`.** No finalize step, no
reopen step. `structure_finalized_at` is stamped automatically by the first generation run.
A structural edit to a course with an `APPROVED` syllabus reverts that syllabus to `DRAFT`
(`m01.service` → `m02.service.invalidate_for_course()`), so the approve gate catches it.

**`approve_and_lock()`** — gains the gate that does not exist today:

> **Approval is refused unless every subject in the program has an `APPROVED` official syllabus.**

Today it locks whatever syllabi happen to exist and returns the count — V1's own verification log
shows `BOARD APPROVE → 200 APPROVED, syllabi_locked=0`, i.e. it will happily lock an empty
curriculum forever. New behaviour: `422 SYLLABUS_INCOMPLETE` naming the subjects still missing one.
**"Every subject" includes every option inside every elective basket.**

On success, one transaction: lock the program, lock every syllabus (`→ LOCKED`), lock every elective
basket, then notify the Dean with the change summary.

**New reads:**
- `get_readiness(program_id)` — per-subject syllabus state. The Board's working surface:
  *42 subjects · 31 with syllabi · 18 approved · 11 untouched*.
- `get_change_summary(program_id)` — derived from the audit log (§2.6), grouped into the Dean-facing
  form: *Added 1 elective · Updated credits on 2 subjects · Shifted 1 subject to Semester 2 ·
  Revised syllabus for 5 courses.*

### 3.2 Bulk syllabus generation

A program's syllabus is **N AI calls**, one per subject — 40+ for an MCA. A batch job, not a request.

- `m02.service.generate_for_program(program_id)` — **refuses unless `structure_finalized_at` is
  set.** Creates a `DRAFT` syllabus for every subject lacking one (core *and* elective options),
  dispatches one Celery task each, returns a batch job id.
- `workers/heavy/syllabus_generation.py` — extended for batch dispatch with per-subject status.
- Partial failure is safe: 37 of 42 succeed → the curriculum stays under review and the Board retries
  the 5. Approval requires all 42 approved anyway, so a half-generated curriculum can never lock.
- Every AI output logs to `AuditLog` with model, `prompt_hash` and output summary (CLAUDE.md rule).

### 3.3 `m02_syllabus/ai_provider.py` — official university format

The current prompt yields AI-notes: 4–6 loose units, topics with `subtopics` and `examples`, no
objectives, no practical components. Rewritten to emit a real university syllabus:

- **Exactly 5 units** (Unit I–V) — the university regulation layout.
- **Course Objectives** (new) — distinct from Course Outcomes.
- **Course Outcomes** CO1…COn with Bloom levels and PO mappings (kept).
- **Practical Components** (new) — populated when the course is a Lab or `hours_practical > 0`.
- **Three bibliography sections** — Text Books, Reference Books, Suggested Reading.
- Unit hours reconcile against the course's derived contact hours.
- Generation reads the **finalized** structure — final credits, final L-T-P, final semester.

The existing safety contract survives unchanged: **the AI never emits DOI, ISBN, author, publisher or
year.** It emits search queries only; CrossRef/OpenLibrary supply real bibliographic metadata.
Enforced by `_validate_result`.

### 3.4 `m01_program_advisor/service.py` — fork carries syllabi forward

`fork_program` (line 480) copies outcomes, baskets, courses and prerequisites — but **not syllabi**.
So today, fixing one typo means v2 starts with zero syllabi and the Board must AI-regenerate all 42.

V2: the fork deep-copies each syllabus (units, COs, CO-PO mappings, references) onto the new
version's courses as `DRAFT`. v2 inherits editable copies; the Board revises rather than regenerates.
v1's syllabi are untouched — they hang off v1's own course rows, so immutability holds by
construction. The fork requires a new `academic_year` + batch (the unique index enforces it).

### 3.5 Already correct — no work needed

Faculty allocation is **already** gated on publication: `is_published_curriculum_course` guards
assignment, `published_course_sql` excludes unpublished programs from Academic Ownership.

---

## 4. API changes

### Deleted

| Route | Why |
|---|---|
| `POST /governance/programs/{id}/return` | The Board never sends work back |
| `POST /syllabi/{id}/submit-for-review` | Faculty do not author syllabi |
| `POST /syllabi/{id}/resubmit` | " |
| `POST /syllabi/{id}/reject` | The Board enhances rather than rejects |
| `POST /syllabi/{id}/request-revision` | " |
| `GET  /syllabi/dean-overview` | The Dean does not review syllabi |

### New

| Method | Route | Who | Does |
|---|---|---|---|
| GET | `/programs/{id}/submission-check` | Dean | **The pre-submission checklist** — what is still missing, and which section fixes it |
| POST | `/governance/programs/{id}/syllabus/generate` | Board | Bulk-generate official syllabi → batch job. Stamps `structure_finalized_at` automatically |
| GET | `/governance/programs/{id}/readiness` | Board | Per-subject syllabus state; drives the workbench and the approve gate |
| GET | `/governance/programs/{id}/changes` | Board + Dean | Change summary, derived from the audit log |
| POST | `/programs/{id}/version` | Dean | Fork v2 (new academic year + batch), syllabi carried forward |
| GET | `/student/curriculum` | Student | Published curriculum, read-only |

### Changed

| Route | Change |
|---|---|
| `POST /programs/{id}/submit` | Requires `academic_year` + `effective_from_batch_id` |
| `POST /governance/programs/{id}/approve` | **Gated on 100% approved syllabi** (422 `SYLLABUS_INCOMPLETE`); locks baskets; notifies Dean with the change summary |
| m01 structural writes | Refused once `structure_finalized_at` is set (409); `program_id` stamped into audit metadata |
| `GET /syllabi/{id}` | Faculty (assigned) + Student (published) read access, official format |
| Elective option add/remove | Refused once the curriculum is locked (409 `CURRICULUM_LOCKED`) |

### Permission matrix

| Action | Dean | Board | Faculty | Student | Admin |
|---|---|---|---|---|---|
| Create program / semesters / credits / courses / baskets | ✅ DRAFT | — | — | — | ✅ |
| Submit to Board | ✅ | — | — | — | ✅ |
| Edit structure after submit | ❌ 403 | ✅ until approval | ❌ | — | ✅ |
| Generate official syllabus | ❌ | ✅ | ❌ | — | ✅ |
| Edit official syllabus | ❌ | ✅ pre-lock | ❌ | — | ✅ |
| Approve + lock | ❌ 403 | ✅ | ❌ | — | ✅ |
| Edit anything after lock | ❌ 409 | ❌ 409 | ❌ 409 | — | ❌ 409 |
| Publish | ✅ | ❌ | ❌ | — | ✅ |
| Assign faculty (post-publish) | ✅ | ❌ | ❌ | — | ✅ |
| Read official syllabus | ✅ | ✅ | ✅ assigned | ✅ published | ✅ |
| Create lesson plan / PPT / notes / course kit / assignments / question papers / marks / attendance | ❌ | ❌ | ✅ | — | — |
| See draft / submitted / under-review curriculum | ✅ own | ✅ | ❌ | ❌ | ✅ |

### No separation of duties inside the Board

Board members are **equal peers with full academic ownership**. There is no department scoping, no
chairman, no hierarchy, and **no second signature**. One member may receive a curriculum, enhance it,
generate and edit the official syllabus, approve it *and* lock it — alone. This is the model, not a
gap: the Board is ONE academic authority, not a ladder of approval levels, and demanding a second
pair of eyes would invent a hierarchy the institution does not have (and stall a curriculum whenever
only one member was available).

**Exactly one person is restricted, and it is not a Board member.** A **Dean can never approve or
lock**, even holding a BOARD grant — enforced in `acts_as_governance()`, not merely hidden in the UI.
The planner must not approve their own plan. The Dean submits, is notified, publishes, and assigns
faculty.

**Accountability comes from the record, not from a restriction.** Every review, modification,
syllabus generation, syllabus approval, curriculum approval and publication is written to the
append-only audit log with its actor, role and timestamp, and is readable as a **Governance Trail**
(`GET /governance/programs/{id}/trail`) — surfaced on the Board's Workbench *and* on the Dean's
Approval tab, because the Dean cannot edit the curriculum they get back and is owed a complete
account of what was done to it. Who did what is never in doubt; it is simply never used to forbid
anything.

Opening the readiness worksheet **is** the act of reviewing, so it is recorded too — deduplicated to
one entry per member per curriculum per day, because the page polls while syllabi generate and an
entry per poll would bury the trail in a table that can never be tidied up.

---

## 5. Frontend

### Dean — minimal change

- Program creation, semesters, courses, elective baskets: **untouched**.
- **Submit to the Board** dialog collects Academic Year + Batch and warns that edit rights are lost.
- After submit — read-only banner: *"With the Board. You will be notified when it is finalized."*
- After approval — *"The Board has reviewed and finalized your curriculum"*, a **What Changed** panel
  (the change summary), and **Publish**. No edit affordance.
- Published — **Create Version 2**.

### Board — the primary new surface

- **Curriculum Review** queue — from V1, kept.
- **Curriculum Workbench** — NEW. One continuous surface, no finalize step:
  *Review Program → Edit Program Structure → Generate Official Syllabus → Review/Edit Official
  Syllabus → Approve Curriculum.* Structure stays editable throughout. *Generate All Missing*, live
  batch progress, per-subject state, and an **Approve Curriculum** button that stays disabled behind
  an explicit checklist until every subject has an approved syllabus. Editing a course whose syllabus
  is approved visibly returns it to Draft, so the Board sees what re-review its own edit created.
- **Official Syllabus Editor** — NEW. University-regulation layout, not a form dump:
  Course Information (code · name · credits · L-T-P · contact hours · category)
  → Course Objectives → Course Outcomes → Unit I–V → Practical Components
  → Text Books → Reference Books → Suggested Reading.

### Faculty — consumption only

- **Assigned Subjects** — exists, kept.
- **Official Syllabus tab** — **read-only**, university layout.
- **Removed:** every syllabus authoring affordance (`CreateSyllabusDialog`, syllabus action bar,
  submit/resubmit/reject hooks). Faculty build lesson plans, PPTs, notes, course kits, assignments,
  question papers, internal marks and attendance — all from the official syllabus.

### Student

- **Published Curriculum** — NEW, read-only: structure by semester + each subject's official
  syllabus. Draft / submitted / under-review curricula are unreachable.

### Vocabulary

No screen hardcodes "Board". Every label comes from `useGovernance()`, so a tenant configured as
`UNIVERSITY_MEMBERS` reads *"Submit to the University Members"*, with identical behaviour.

---

## 6. Migration strategy

`0084ten_governance_v2.py`, ordered:

1. `programs`: `academic_year`, `structure_finalized_at`, `structure_finalized_by_user_id`
2. `UPDATE programs SET status='DRAFT' WHERE status='RETURNED'`
3. `syllabi`: add `objectives`, `practical_components`; rename `dean_comment → board_comment`
4. `syllabi.status` data migration (§2.3)
5. `elective_baskets`: `locked_at`, `locked_by_user_id`; backfill for already-approved programs
6. `CREATE UNIQUE INDEX uq_programs_curriculum_version`

**Grandfathering (explicit).** Existing published curricula are **not modified and not invalidated**.
They predate the syllabus-completeness gate and may have zero syllabi; they keep working exactly as
they do today. The gate applies to approvals from now on, never retroactively. Their next version
goes through the full V2 workflow. `academic_year` backfills from the linked batch where one exists,
otherwise stays NULL — the unique index is partial and ignores NULLs, so legacy rows can't collide.

**Down-migration** restores columns but cannot restore collapsed status values — noted in the
docstring.

---

## 7. Removal of the obsolete workflow

Deleted outright, not deprecated — a removed workflow left in the tree is how it comes back.

**Backend**
- `governance/service.py` — `return_to_dean()`, the `RETURNED` write path
- `m01/models.py` — `ProgramStatus.RETURNED`
- `m02/models.py` — `SyllabusStatus.PENDING_REVIEW`, `.REJECTED`, `.DEAN_APPROVED`, `.DEAN_LOCKED`
- `m02/service.py` — `submit_for_review()`, `resubmit()`, `reject()`, `request_revision()`
- `m02/router.py` — the 5 endpoints in §4; the `_DEAN` / `_LOCK` legacy aliases
- `m02/schemas.py` — `RejectRequest`, `RequestRevisionRequest`, `SyllabusDeanItem`,
  `SyllabusDeanOverviewResponse`
- `notifications/models.py` — drop `SYLLABUS_REJECTED`, `SYLLABUS_REVISION_REQUESTED`,
  `SYLLABUS_SUBMITTED`; **add** `CURRICULUM_FINALIZED` (Board → Dean)

**Frontend** — `CreateSyllabusDialog.tsx`, `SyllabusActionBar.tsx`, `SyllabusActionDialogs.tsx`,
the submit/resubmit/reject hooks in `useSyllabusActions.ts`, and the Dean syllabus-review dashboard.

**Tests** — m02 router/service tests covering deleted transitions are rewritten, not deleted.

---

## 8. Manual testing plan

**Setup**
- [ ] Tenant with governance type **Board**; a second with **University Members**. Labels follow the
      tenant; behaviour identical.
- [ ] Onboard a `BOARD` user; grant `BOARD` to an existing Faculty — both reach the Board workspace.
- [ ] A **Dean** never sees the Board workspace, even holding a BOARD grant.
- [ ] Every Board member can open every curriculum — no department scoping, no hierarchy.

**Dean plans (existing flow — regression check)**
- [ ] Create MCA / 120 credits / 4 semesters; add core subjects with credits and L-T-P; add an
      elective basket with 3 options. **The form is exactly as it was** — no new fields.
- [ ] The Dean has no syllabus affordance anywhere.
- [ ] Submit without Academic Year / Batch → blocked.
- [ ] Submit a non-compliant curriculum → 422 with the compliance message.
- [ ] Submit MCA / 2026-2028 / v1 → **Under Board Review**; warned edit rights are lost.

**Dean is locked out**
- [ ] Edit title / add subject / edit basket → **403**. Delete unavailable. No API bypass.

**Board enhances**
- [ ] Board queue shows MCA with correct subject / elective / credit counts and the submitter.
- [ ] Board enhances: add a subject, remove one, shift one to Semester 2, adjust credits, add an
      elective option → all succeed.
- [ ] There is **no "Finalize Structure" button anywhere** — the Board goes straight from editing to
      generating.
- [ ] Structure stays editable right up to approval; no mid-flight freeze.
- [ ] After generating, edit a course whose syllabus is `APPROVED` → **that syllabus reverts to
      `DRAFT`** and approval is blocked until it is re-reviewed. A stale syllabus can never be locked.

**Board generates and finalizes the syllabus**
- [ ] Generate → batch job; progress visible; every subject **including every elective option** gets
      a syllabus.
- [ ] Kill one generation mid-flight → curriculum stays under review; that subject is retryable.
- [ ] Output is in **university format**: Course Information (code · name · credits · L-T-P ·
      **derived** contact hours · **derived** category), Course Objectives, CO1…, Unit I–V, Practical
      Components, Text Books, Reference Books, Suggested Reading.
- [ ] Contact hours = (L+T+P) × 15 and category is one of Core / Elective / Lab / Project — neither
      was ever typed in by anyone.
- [ ] No AI-invented DOI / ISBN / author / publisher anywhere.
- [ ] Board edits a syllabus (units, COs, books) → succeeds.
- [ ] **Faculty cannot edit that syllabus (403)**; can read it.

**The approve gate**
- [ ] Approve with syllabi missing → **422 `SYLLABUS_INCOMPLETE`**, naming exactly which subjects.
- [ ] Approve with one elective option missing a syllabus → also blocked.
- [ ] A Dean hitting the approve endpoint directly → **403**. This is the only restriction in the
      model, and it holds even when the Dean also holds a BOARD grant.
- [ ] All syllabi approved → **Approve Curriculum** succeeds.

**No separation of duties inside the Board**
- [ ] **One member does everything, alone:** the same board member reviews the curriculum, modifies
      the structure, generates the syllabus, edits it, approves every subject, and then approves and
      locks the curriculum. **No second signature is required and none is asked for.**
- [ ] A second board member can do exactly the same on another curriculum. They are equal peers —
      no chairman, no hierarchy, no department scoping.

**The governance trail (accountability without restriction)**
- [ ] Board → Workbench → **Governance Trail** lists every action with a named actor, their role,
      and a timestamp.
- [ ] It records **who reviewed** (opening the workbench is the review act), **who modified**,
      **who approved**, and **who published**.
- [ ] Opening the workbench repeatedly does **not** spam the trail — one review entry per member per
      curriculum per day.
- [ ] Dean → program → **Approval** tab shows the same trail. The Dean cannot edit this curriculum
      and can only publish it, so they can see exactly what was done to it and by whom.
- [ ] Admin → Audit Logs contains the same events. Nothing in the trail can be edited or deleted —
      it is read straight from the append-only audit log.

**Locked means locked**
- [ ] Dean edit → 409. Board edit → 409. Admin edit → 409. Syllabus edit → 409.
- [ ] Add a new elective option to a locked basket → **409**.

**Dean publishes**
- [ ] Dean is notified: *"Board has reviewed and finalized your curriculum."*
- [ ] **What Changed** lists every Board enhancement, derived from the audit log.
- [ ] Dean publishes. Publishing does **not** unlock editing.
- [ ] Dean assigns faculty — only now are subjects assignable.
- [ ] Faculty see assigned subjects + read-only official syllabus; build a course kit against it.
- [ ] Students see only the published curriculum.

**Versioning**
- [ ] Create Version 2 → opens as **DRAFT** owned by the Dean, syllabi **carried forward** as
      editable copies, not regenerated.
- [ ] v2 requires a different batch (uniqueness enforced).
- [ ] **v1 stays PUBLISHED and untouched.** Students on the 2026-2028 batch still see v1.

**Grandfathering**
- [ ] Every pre-existing published curriculum still works: faculty assigned, students see it,
      timetable/attendance/marks unaffected. Nothing was invalidated.

**Audit**
- [ ] `CURRICULUM_SUBMITTED / APPROVED / LOCKED / PUBLISHED` logged with the right actors.
- [ ] Every AI generation logged with model + `prompt_hash` + output summary.
- [ ] The change summary is reconstructable from the audit log alone.

**Regression** — timetable, attendance, internal marks, course kits, learning materials,
notifications, student dashboard all still work.

---

## 8b. Two holes found while building, and closed

Both were ways an unreviewed document could reach students inside a "locked" curriculum. Neither was
in the plan; both were found by writing the tests.

**1. Editing a syllabus's units or outcomes left it APPROVED.**

`update_syllabus` returned an edited syllabus to DRAFT, but the child mutations — add a unit, delete
a course outcome, change a CO-PO mapping, add a reference — did not. So the Board could approve a
syllabus, rewrite every unit in it, and the approval would still stand. The curriculum's approve gate
would then pass on a document nobody had read in its current form, which makes the gate worthless.

Fixed by moving the un-approval into `_require_mutable`, the single function every syllabus write
already passes through. It is now structurally impossible for a write path to forget: you cannot edit
any part of a syllabus without its approval falling away.

**2. A new syllabus could be created inside a locked curriculum.**

`create_syllabus` and `fork` had no curriculum-lock check — only *edits* were guarded. A Board member
could therefore add a brand-new syllabus to a course in an approved, published curriculum, approve
it, and it would become the latest official syllabus that Faculty teach from and Students read. The
lock guarded the front door and left the side door open.

Fixed with `_require_curriculum_unlocked`, called by both. Changing a locked curriculum means forking
the **curriculum** (which copies its syllabi onto the new version's own course rows), never forking a
syllabus underneath one.

**3. A latent test-harness bug that would have broken CI (pre-existing, not mine).**

`tenant_db_a` in both the m01 and m02 conftests set the tenant `search_path` **once**, session-level,
at fixture setup. But every service method commits, and a commit returns the connection to the pool —
so the next statement can check out a *different* connection that never saw that `SET`. The suites
passed when run file-by-file (the pool handed back the same connection each time) and failed the
moment another test file churned the pool first, with a bewildering `relation "programs" does not
exist`. Twenty-four tests failed in the full run and zero failed individually.

The app already solves this properly — `_tenant_schema_ctx` is a ContextVar that the engine's `begin`
event reads to inject `SET LOCAL search_path` on **every** transaction, precisely because a pooled
connection can change underneath you. The fixtures now use that same mechanism instead of working
around it.

---

## 9. Files to be touched

**Backend — modified:** `core/governance/{models,schemas,service,router}.py` ·
`core/audit_log/models.py` · `core/notifications/models.py` ·
`m01_program_advisor/{models,schemas,service,router}.py` ·
`m02_syllabus/{models,schemas,service,router,ai_provider}.py` ·
`m_academics/elective_service.py` · `workers/heavy/syllabus_generation.py`

**Backend — new:** `alembic/tenant_versions/0084ten_governance_v2.py` ·
`m02_syllabus/formatting.py` (derived category + contact hours, official-format assembly)

**Frontend — new:** Board Curriculum Workbench · Official Syllabus Editor · Official Syllabus
(read-only) view · Student Published Curriculum page · Dean What-Changed panel

**Frontend — modified:** program ActionBar / ApprovalPanel · syllabus pages · faculty subject
workspace · governance API client, hooks and types

**Frontend — deleted:** `CreateSyllabusDialog.tsx` · `SyllabusActionBar.tsx` ·
`SyllabusActionDialogs.tsx` · faculty syllabus-authoring hooks

---

**Nothing will be committed.** Implementation begins only on approval.
