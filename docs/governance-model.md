# Governance Model — Roles & Responsibilities

_Last updated: 2026-06-19 (governance & usability correction pass)._

Vidya separates **primary roles** (who you are — set on the Users page, gates
login and base navigation) from **responsibilities** (what you may additionally
do — layered onto a FACULTY login via `faculty_role_grants`).

## Primary roles (`users.role`)

| Role    | Scope |
|---------|-------|
| ADMIN   | Institution operations: onboarding, imports, settings, branding, data validation. |
| DEAN    | Academic governance: programs, syllabus/approval, results, analytics. |
| FACULTY | Teaching staff; the base account that can carry responsibilities. |
| STUDENT | Learner portal. |
| BOARD   | **Legacy primary role — under review (see below).** |

GUIDE / EVALUATOR / BOARD are **not** assignable as primary roles on the Users
page. Legacy standalone accounts still display with a migration hint.

## Responsibilities (`faculty_role_grants`, layered on a FACULTY login)

| Responsibility | Who may grant/revoke |
|----------------|----------------------|
| GUIDE          | ADMIN or DEAN |
| EVALUATOR      | ADMIN or DEAN |
| BOARD          | ADMIN only |

One FACULTY login can hold several active responsibilities simultaneously and
role-switch into each existing workflow. DEAN is a primary role, never a grant.

## Faculty → department membership

A faculty belongs to a department if their profile `primary_department_id`
matches **or** they have an active program assignment to a program in that
department. `primary_department_id` is derived (NULL-only, never overwriting a
Dean-set value) from the faculty's first resolved program at CSV import, and
backfilled for existing faculty from active program assignments. This is what
makes the Faculty Directory department filter return results.

---

## TODO — open governance items (do not implement without sign-off)

### BOARD governance — UNDER REVIEW
BOARD governance remains under review. The current implementation (BOARD as an
ADMIN-only responsibility grant on a FACULTY account) **remains unchanged until a
final BOARD architecture is approved.**

Approved direction (to be built as separate future work, _not_ in this pass):
an external **board-member registry** (`board_members`) decoupled from `users`,
so external people — External Examiner, Industry Expert, University Nominee,
Academic Council Member — can serve on a board **without** requiring FACULTY
status or a login. Internal faculty link via an optional `user_id`; the existing
faculty BOARD grant coexists as an `INTERNAL_FACULTY` source. Impact: 1 new
tenant table + migration, board-session linkage refactor, a small admin page.

### Per-Dean department scoping — DEFERRED
Today a DEAN governs the entire tenant (no Dean→department mapping exists). True
"a Dean sees only the departments they govern" scoping needs a new
`dean_departments` model and query scoping. Deferred — the directory department
filter bug is fixed independently of this.
