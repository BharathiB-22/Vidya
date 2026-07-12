# Phase A — Academic Governance V1

**Status:** Implemented, verified end-to-end, **not committed** (awaiting manual testing sign-off).
**Branch:** `feature/erp-onboarding`

---

## The one-line change

**The Dean no longer owns the final curriculum.** The Dean *prepares* it and *submits* it; the
governance authority (Board / University Members) *reviews, modifies, approves and locks* it; only
then does the Dean *publish* it.

Before Phase A the same Dean created, approved and published curriculum — a human gate existed, but
the same human passed it. That is gone.

```
Dean                                 Governance (Board / University Members)
────                                 ───────────────────────────────────────
Create Program (DRAFT)
Semesters, Subjects, Credits,
Labs, Projects, Elective Baskets
        │
        └── Submit ────────────────► PENDING_APPROVAL
                                     Review · Modify credits/units/hours
                                     Generate & edit syllabus
                                         │
        ◄── Return (w/ comments) ────────┤  RETURNED → Dean edits → resubmit (new cycle)
                                         │
                                         └── Approve ──► APPROVED + LOCKED
                                                          (curriculum AND its syllabi frozen)
        │
        └── Publish ──────────────────────────────────► PUBLISHED
                                                        Faculty receive assigned subjects
```

Locked means locked: after approval **nobody** edits — not the Dean, not the Board. A change is a
new version (fork), which lands back in the Dean's hands as a Draft.

---

## 1. Files changed

### Backend — new

| File | Purpose |
|---|---|
| `backend/app/core/governance/__init__.py` | new module |
| `backend/app/core/governance/models.py` | `CurriculumApprovalRequest` — append-only submit→decide ledger |
| `backend/app/core/governance/schemas.py` | `GovernanceInfo`, queue, approve/return/submit payloads |
| `backend/app/core/governance/service.py` | ownership state machine + separation-of-duties rules |
| `backend/app/core/governance/router.py` | `/governance/*` |
| `backend/alembic/public_versions/0017_public_tenant_governance_type.py` | `tenants.governance_type` |
| `backend/alembic/tenant_versions/0083ten_curriculum_governance.py` | program governance columns + approval table |
| `backend/tests/core/test_governance.py` | vocabulary, queue access, Board-grant membership |

### Backend — modified

| File | Change |
|---|---|
| `app/core/auth/models.py` | `GovernanceType` enum; `Tenant.governance_type` |
| `app/core/tenants/{schemas,repository,service}.py` | governance type on tenant create/update/read |
| `app/core/audit_log/models.py` | `CURRICULUM_SUBMITTED/RETURNED/APPROVED/LOCKED` |
| `app/modules/m01_program_advisor/models.py` | `RETURNED` status; submitted/locked/regulation columns |
| `app/modules/m01_program_advisor/router.py` | **removed** Dean `approve`/`reject`; **added** `submit`; new `assert_can_edit_structure` role+status gate |
| `app/modules/m01_program_advisor/service.py` | **removed** `ProgramService.approve`/`reject`; role-aware edit windows |
| `app/modules/m01_program_advisor/{schemas,repository}.py` | new fields |
| `app/modules/m02_syllabus/router.py` | syllabus write/approve/lock: Faculty+Dean → **governance** |
| `app/workers/heavy/program_structure.py` | AI generation lands in **DRAFT**, not PENDING_APPROVAL |
| `app/workers/heavy/program_export.py` | export allowed for APPROVED **and** PUBLISHED (was a latent bug) |
| `tests/modules/m01_program_advisor/*`, `tests/modules/m02_syllabus/*` | rewritten to the new ownership model |

### Frontend — new

`types/governance.ts` · `lib/api/governance.ts` · `hooks/governance/index.ts` · `lib/governance.tsx`
(vocabulary context) · `components/governance/GovernanceDialogs.tsx` ·
`pages/governance/GovernanceQueuePage.tsx` · `pages/governance/ApprovedCurriculaPage.tsx`

### Frontend — modified

`main.tsx` (GovernanceProvider) · `App.tsx` (routes) · `lib/workspace.tsx` (BOARD workspace) ·
`components/shell/Sidebar.tsx` (Academic Governance section) ·
`components/programs/ActionBar.tsx` (rewritten around ownership) ·
`components/programs/ApprovalPanel.tsx` (pipeline + review-cycle history) ·
`components/programs/ProgramStatusBadge.tsx` · `types/program.ts` · `lib/api/programs.ts` ·
`hooks/programs/useProgramActions.ts` (approve/reject hooks deleted) ·
`pages/admin/TenantCreatePage.tsx` + `lib/api/tenants.ts` (governance type picker)

---

## 2. Database changes

**`public.tenants`** (migration `0017pub`)

```
+ governance_type  VARCHAR(30)  NOT NULL  DEFAULT 'BOARD'   -- BOARD | UNIVERSITY_MEMBERS
```

Display name only. Both values are byte-for-byte identical in permissions. Existing tenants default
to `BOARD`.

**`programs`** (migration `0083ten`)

```
+ submitted_by_user_id     UUID          -- the Dean who submitted
+ submitted_at             TIMESTAMPTZ
+ locked_by_user_id        UUID          -- the governance member who locked it
+ locked_at                TIMESTAMPTZ
+ review_comment           TEXT          -- last return/approve note
+ regulation_year          INTEGER       -- e.g. 2026 → "R2026"
+ effective_from_batch_id  UUID → acad_batches(id) ON DELETE SET NULL
```

`programs.status` gains **`RETURNED`** (stored as a string; the enum is `native_enum=False`, so no
type migration and no existing row can hold it).

**`curriculum_approval_requests`** (new, tenant schema)

```
id, program_id → programs(id) CASCADE,
cycle INT,                    -- 1, then 2 after a return+resubmit, …
status VARCHAR(20),           -- PENDING → APPROVED | RETURNED
submitted_by_user_id, submitted_at, submission_note,
decided_by_user_id,  decided_at,  decision_comment,
created_at

UNIQUE (program_id, cycle)
UNIQUE (program_id) WHERE status = 'PENDING'   -- at most ONE open request per curriculum
```

Append-only: rows are never deleted and a decided cycle is never reopened. A resubmit opens a *new*
cycle, so the full negotiation between Dean and Board is on the record.

---

## 3. API changes

### New — `/governance`

| Method | Route | Who | Does |
|---|---|---|---|
| GET | `/governance/info` | any tenant user | returns `{governance_type, body_label, member_label}` — drives every label in the UI |
| GET | `/governance/queue` | governance only | pending / approved / published curricula with counts |
| POST | `/governance/programs/{id}/approve` | governance only | approve **and lock** curriculum + all its syllabi |
| POST | `/governance/programs/{id}/return` | governance only | back to the Dean; **comment mandatory** |
| GET | `/governance/programs/{id}/history` | Dean, Admin, Faculty, governance | every submit→decide cycle |

### Changed — `/programs`

| Route | Before | After |
|---|---|---|
| `POST /programs/{id}/submit` | — | **new.** Dean: DRAFT\|RETURNED → PENDING_APPROVAL (compliance-gated) |
| `POST /programs/{id}/approve` | Dean approved | **deleted (404).** Approving is a governance act |
| `POST /programs/{id}/reject` | Dean rejected | **deleted (404).** Replaced by governance *return* |
| `POST /programs/{id}/publish` | Dean | unchanged — Dean still publishes |
| All structural writes (courses, outcomes, credits, baskets) | ADMIN+DEAN, any pre-publish status | gated by `assert_can_edit_structure`: **Dean** in DRAFT/RETURNED, **governance** in PENDING_APPROVAL, **nobody** once APPROVED (409 `CURRICULUM_LOCKED`) |
| `GET /programs*` | ADMIN, DEAN, FACULTY | + **BOARD** |

New error codes: `AWAITING_GOVERNANCE` (403, Dean edited a submitted curriculum), `CURRICULUM_LOCKED`
(409), `NOT_GOVERNANCE` (403), `SELF_APPROVAL` (403).

### Changed — `/syllabi`

The syllabus is curriculum, so it moved with the curriculum:

| | Before | After |
|---|---|---|
| create / edit / AI-generate / submit | ADMIN + **FACULTY** | ADMIN + **BOARD** |
| approve / reject / lock / unlock | **DEAN** | **BOARD** (via `require_responsibility`, so a professor holding a BOARD grant qualifies) |
| read | ADMIN, DEAN, FACULTY | + BOARD |

**Faculty no longer write syllabi.** They teach to the approved syllabus and build course kits,
lesson plans, assignments and assessments under it.

### Changed — `/tenants`

`POST /tenants` and `PATCH /tenants/{id}` accept `governance_type`; `TenantResponse` returns it.

---

## 4. UI changes

**Platform Admin → Provision University**: a governance-authority picker (Board / University
Members) with a note that it is a display name only.

**New BOARD workspace** (`lib/workspace.tsx`) with its own sidebar section, *Academic Governance*:
- **Curriculum Review** (`/governance/curriculum`) — the queue that could not exist before, because
  curriculum used to be approved by the person who wrote it. Stat tiles + premium cards showing
  subject/elective/syllabus/credit counts, who submitted and their note. Empty states included.
- **Approved Curricula** (`/governance/approved`) — locked and published curricula, read-only.
- **Syllabuses** — governance now owns these.

**Dean's program page** (`ActionBar`): *Generate with AI · Edit · Delete · **Submit to the Board*** in
DRAFT/RETURNED; a read-only banner while under review; ***Publish*** once approved. A returned
curriculum shows the governance authority's comment in an amber callout at the top — the most
important thing on the page when work comes back.

**Board's program page**: the same page, but ***Approve & Lock*** · ***Return to Dean*** · ***Modify***.
The approve dialog states plainly that approval freezes the curriculum and its syllabi for everyone.

**Approval tab**: pipeline now reads *Prepared by Dean → Under Board Review → Approved & Locked →
Published*, with the acting role under each step, plus a **Review History** of every submit→decide
cycle with both parties' comments.

**Vocabulary**: no screen hardcodes "Board". Every label comes from `useGovernance()`, so a tenant
configured as `UNIVERSITY_MEMBERS` reads "Submit to the University Members", "University Member",
etc., with identical behaviour.

**Headings**: governance surfaces use **bold black** headings (`text-black font-bold`) — no grey
titles — on white cards with `rounded-xl`, hairline borders and hover elevation.

---

## 5. Manual testing checklist

Prerequisite: run the app; migrations apply on startup (`0017pub`, `0083ten` — both verified applied).

**Governance type**
- [ ] Platform Admin → Provision University → pick **Board**; create. UI says "Board" / "Board Member".
- [ ] Provision a second tenant with **University Members**; every governance label in that tenant reads "University Members". Behaviour identical.

**Roles**
- [ ] Admin → onboard a `BOARD` user; and grant `BOARD` to an existing Faculty (both must work).
- [ ] Faculty-with-BOARD-grant sees the governance workspace in the workspace switcher; a plain Faculty does not.
- [ ] A **Dean** never sees the governance workspace, even if granted BOARD.

**Dean prepares**
- [ ] Dean → Programs → create a program (set Regulation Year).
- [ ] Add semesters/subjects/credits/labs/projects; add an elective basket with 2–3 choices.
- [ ] "Generate with AI" → when it finishes the program is **DRAFT** (not auto-submitted).
- [ ] Submit with an incomplete curriculum → blocked with a compliance message (422).
- [ ] Submit a compliant one → status **Under Review**; a warning explained the Dean loses edit rights.

**Dean is locked out**
- [ ] As Dean, try to edit the title / add a subject / edit a basket → blocked (403, "owned by the Board").
- [ ] Delete is unavailable for a submitted curriculum.

**Governance reviews**
- [ ] Board → Curriculum Review → the curriculum appears in **Pending** with correct counts, submitter and note.
- [ ] Board opens it and **modifies** credits / a subject / teaching hours → succeeds.
- [ ] Board generates/edits the **syllabus** for a subject (units, COs, references, hours) → succeeds.
- [ ] **Faculty cannot edit that syllabus** (403) but can read it.
- [ ] Board → **Return to Dean** with no comment → blocked (comment mandatory).
- [ ] Return with a comment → Dean sees status **Returned** and the comment in the amber callout; Dean can edit again.
- [ ] Dean resubmits → Approval tab shows **Cycle 2**, with cycle 1 recorded as Returned.

**Approve + lock**
- [ ] A Dean hitting the governance approve endpoint is refused (403) — the button is not shown, and the API refuses it too.
- [ ] The Board member **who submitted** it cannot approve it (403 `SELF_APPROVAL`) — needs a second member.
- [ ] Board → **Approve & Lock** → status **Approved & Locked**; toast reports how many syllabi were frozen.
- [ ] After approval: Dean **and** Board are both blocked from editing (409 `CURRICULUM_LOCKED`).
- [ ] The subject's syllabus is now **DEAN_LOCKED** (frozen) and cannot be edited by anyone.

**Publish + versioning**
- [ ] Dean → **Publish** → status **Published**; Faculty see their assigned subjects; students see electives.
- [ ] Export a published curriculum (PDF/DOCX) → succeeds.
- [ ] "Create New Version" → v2 opens as a **DRAFT** owned by the Dean, unapproved and unlocked; v1 stays Published and untouched.
- [ ] Approval tab → Version History shows v1 Published, v2 Draft.

**Audit**
- [ ] Admin → Audit Logs shows `CURRICULUM_SUBMITTED`, `CURRICULUM_RETURNED`, `CURRICULUM_APPROVED`, `CURRICULUM_LOCKED` with the right actors.

---

## 6. Verification already done

- **Frontend**: `tsc --noEmit` clean; `npm run build` succeeds.
- **Migrations**: both applied to real tenant schemas (including `tenant_vbs_university`); existing tenants defaulted to `BOARD`.
- **End-to-end over HTTP against the real DB** (seed data cleaned up afterwards):

  ```
  VOCAB                  {'governance_type':'BOARD','body_label':'Board',…}
  CREATE                 201 DRAFT
  SUBMIT (Dean)          200 PENDING_APPROVAL
  DEAN EDIT after submit 403        ← Dean locked out
  QUEUE (Board)          200 pending=1
  BOARD MODIFY           200        ← Board revises it
  DEAN APPROVE           403        ← separation of duties holds
  BOARD APPROVE          200 APPROVED, syllabi_locked=0
  EDIT after lock        409        ← locked for everyone
  DEAN PUBLISH           200 PUBLISHED
  HISTORY                [(1,'APPROVED')]
  ```

- **Backend tests**: m01 service 29/29, m01 router 28/28, m02 router green except two pre-existing
  failures (below).

### Known pre-existing failures (NOT caused by Phase A)

Both were verified against `HEAD` and are unrelated to governance — they belong to the in-flight
syllabus refactor already sitting uncommitted on this branch:

1. `m02 :: test_dean_can_read_syllabus_list` — a Dean with no `dean_program_assignments` gets 403
   `NOT_IN_SCOPE`. The scoping code is committed at HEAD and my diff does not touch it.
2. `m02 :: test_reject_returns_201_with_new_draft` — expects reject to fork a new draft (201); the
   endpoint at HEAD returns 200 and sets `REJECTED`.

I left both alone rather than paper over them. They need a separate decision.

Also corrected: `m01 :: test_unauthenticated_returns_422` asserted 422, but the endpoint returns
**401** for a request with no credentials (and always did — `list_programs` is byte-identical to
HEAD). The assertion was describing the wrong dependency; it now asserts 401.

---

## 7. Deliberately out of scope

No changes to attendance, marks, timetable, course kits, faculty workspace, student workspace, or any
UI outside governance — as specified.

**Nothing is committed.** Awaiting manual testing sign-off.
