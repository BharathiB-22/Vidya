"""Academic Governance — service layer (Phase A V2).

Who owns what
-------------
    Dean        the academic PLANNER. Creates the program structure — semesters,
                credits, core subjects, elective baskets — and SUBMITS it. Once
                submitted the Dean is read-only on that curriculum version,
                permanently. After approval the Dean publishes it. That is all.
    Board       the academic OWNER (Board / University Members — the name is a
                per-tenant display choice, see auth.models.GovernanceType).
                Reviews the submitted structure, ENHANCES it where the academics
                require, generates the official syllabus, edits and approves it,
                then approves the curriculum, which LOCKS it.

The Board does not reject, return, or request changes — there is no path back to
the Dean. When the Board finds the Dean's plan wanting it improves the plan
itself: rearranging semesters, adjusting credits, refining subject flow, adding
or removing electives. That is what an academic authority is for. The Dean is
then told exactly what changed (`get_change_summary`) before publishing.

Exactly one person is restricted, and it is not a Board member:

  * A user whose base role is DEAN can never act as the Board, even holding a
    BOARD grant — the planner must not approve their own plan.

Inside the Board there is NO separation of duties. All members are equal peers:
no department scoping, no hierarchy, no chairman, no second signature. One member
may receive a curriculum, enhance it, generate and edit the official syllabus,
approve it and lock it — alone. The Board is ONE academic authority, not a ladder
of approval levels, and requiring a second pair of eyes would invent a hierarchy
the institution does not have.

Accountability comes from the RECORD instead of from a restriction: every review,
modification, syllabus edit, syllabus approval and curriculum approval is written
to the append-only audit log with its actor, role and timestamp, and is readable
as a governance trail (`get_audit_trail`). Who did what is never in doubt — it is
simply never used to forbid anything.

The approve gate
----------------
`approve_and_lock` refuses unless EVERY subject in the program — core courses and
every option inside every elective basket — has an APPROVED official syllabus.
This is the single invariant of Phase A, and everything else leans on it:

    add a course        -> it has no syllabus          -> approval blocked
    edit a course       -> its syllabus reverts to DRAFT -> approval blocked
    delete a course     -> its syllabus cascades away  -> nothing to block
    elective option added -> it has no syllabus        -> approval blocked

which is why the Board needs no structure freeze while it works, and why a stale
or missing syllabus can never end up inside a locked curriculum.
"""
from __future__ import annotations

import logging
from uuid import UUID, uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import GovernanceType, TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.governance.schemas import (
    ChecklistItem,
    ChangeSummary,
    ChangeSummaryLine,
    GovernanceInfo,
    QueueItem,
    ReadinessItem,
    ReadinessSummary,
    SubmissionCheckItem,
    SubmissionChecklist,
    TrailEntry,
)
from app.modules.m01_program_advisor.models import (
    EXECUTION_TYPES,
    CourseType,
    Program,
    ProgramStatus,
    is_execution_document,
)
from app.modules.m02_syllabus.ai_provider import (
    MIN_TOPICS_PER_UNIT,
    normalize_course_type,
)
from app.modules.m02_syllabus.formatting import roman

logger = logging.getLogger("vidya.governance")


class GovernanceServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


async def _commit(db: AsyncSession, program_id: UUID) -> None:
    """Commit, then re-read the Program we just mutated.

    The state transitions here are written as raw UPDATEs (each touches several
    tables at once). The app's sessions are built with `expire_on_commit=False`,
    so a `Program` already loaded in this session keeps its stale in-memory
    `.status` after such an UPDATE — a caller re-reading the program through the
    ORM in the same request would be handed DRAFT right after a successful
    submit. An awaited `refresh` repopulates it from the database.

    (`expire_all()` would also work in a sync session, but in asyncio an expired
    attribute would lazy-load on plain attribute access and raise MissingGreenlet.
    Refresh does the IO here, where we can await it.)
    """
    await db.commit()
    program = await db.get(Program, program_id)
    if program is not None:
        await db.refresh(program)


# ---------------------------------------------------------------------------
# Vocabulary — Board vs University Members is a label, never a behaviour
# ---------------------------------------------------------------------------

_LABELS: dict[GovernanceType, tuple[str, str]] = {
    GovernanceType.BOARD:              ("Board",              "Board Member"),
    GovernanceType.UNIVERSITY_MEMBERS: ("University Members", "University Member"),
}


def labels_for(governance_type: GovernanceType) -> tuple[str, str]:
    return _LABELS.get(governance_type, _LABELS[GovernanceType.BOARD])


async def get_governance_info(tenant_id: UUID | None, db: AsyncSession) -> GovernanceInfo:
    """Read the tenant's governance vocabulary. Falls back to BOARD."""
    gtype = GovernanceType.BOARD
    if tenant_id is not None:
        row = (
            await db.execute(
                text("SELECT governance_type FROM public.tenants WHERE id = :tid"),
                {"tid": str(tenant_id)},
            )
        ).first()
        if row and row[0]:
            try:
                gtype = GovernanceType(row[0])
            except ValueError:
                gtype = GovernanceType.BOARD
    body, member = labels_for(gtype)
    return GovernanceInfo(governance_type=gtype, body_label=body, member_label=member)


# ---------------------------------------------------------------------------
# Who counts as a Board member
# ---------------------------------------------------------------------------

async def acts_as_governance(user: CurrentUser, db: AsyncSession) -> bool:
    """True if `user` may exercise Board authority in this tenant.

    A Board member is a user whose base role is BOARD, or any user holding an
    active BOARD grant (faculty_role_grants) — real Boards of Studies are staffed
    by senior faculty, so a professor sitting on the Board keeps ONE account.

    All Board members are equal: no department scoping, no seniority, no
    chairman. Any member may act on any curriculum.

    A DEAN is explicitly excluded even when they hold a BOARD grant: the Dean
    authors the plan, so letting them approve it would restore exactly the
    self-approval this phase exists to remove.
    """
    if user.role == TenantRole.DEAN.value:
        return False
    if user.is_super_admin or user.role == TenantRole.BOARD.value:
        return True
    row = (
        await db.execute(
            text(
                "SELECT 1 FROM faculty_role_grants "
                "WHERE faculty_user_id = :u AND role_code = 'BOARD' AND is_active = true LIMIT 1"
            ),
            {"u": str(user.user_id)},
        )
    ).first()
    return row is not None


async def require_governance(user: CurrentUser, db: AsyncSession) -> None:
    if not await acts_as_governance(user, db):
        raise GovernanceServiceError(
            "NOT_GOVERNANCE",
            "Only the academic governance authority may perform this action. "
            "A Dean may not approve curriculum they prepared.",
            403,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def get_program_status(program_id: UUID, db: AsyncSession) -> str:
    """The curriculum's lifecycle state — DRAFT … APPROVED … PUBLISHED.

    Public because the Dean's publish gate needs it and has no business reaching into a
    private helper to get it.
    """
    program = await _get_program(program_id, db)
    return str(program.status)


async def _get_program(program_id: UUID, db: AsyncSession):
    row = (
        await db.execute(
            text(
                "SELECT id, title, status, version, duration_years, academic_year, "
                "       effective_from_batch_id, submitted_by_user_id, submitted_at "
                "FROM programs WHERE id = :p"
            ),
            {"p": str(program_id)},
        )
    ).first()
    if row is None:
        raise GovernanceServiceError("NOT_FOUND", "Program not found.", 404)
    return row


async def _require_program_status(program_id: UUID, expected: ProgramStatus, db: AsyncSession):
    program = await _get_program(program_id, db)
    if program.status != expected.value:
        raise GovernanceServiceError(
            "INVALID_STATUS",
            f"Curriculum must be {expected.value} for this action; it is {program.status}.",
            409,
        )
    return program


async def _open_request(program_id: UUID, db: AsyncSession):
    return (
        await db.execute(
            text(
                "SELECT id, cycle, submitted_by_user_id FROM curriculum_approval_requests "
                "WHERE program_id = :p AND status = 'PENDING'"
            ),
            {"p": str(program_id)},
        )
    ).first()


# Every subject in a curriculum: core courses AND every option inside every
# elective basket. An elective option is a real course a student sits and is
# examined in, so it needs its own official syllabus exactly as a core course
# does. Getting this wrong is how a subject with no Board-approved syllabus ends
# up inside a locked curriculum, so both the readiness view and the approve gate
# read this one definition.
_ALL_SUBJECTS_SQL = """
SELECT c.id            AS course_id,
       c.code,
       c.title,
       c.semester,
       c.is_elective,
       c.course_type,
       c.hours_practical,
       eb.name         AS basket_name,
       s.id            AS syllabus_id,
       s.status        AS syllabus_status,
       s.doc_type,
       s.document,
       s.objectives,
       s.practical_components,
       s.outcome_count,
       s.expected_units,
       s.unit_hours,
       s.unit_count,
       s.present_units,
       s.weak_units,
       s.reference_count,
       s.textbook_count,
       s.refbook_count,
       s.dean_edited_at
FROM courses c
LEFT JOIN elective_baskets eb ON eb.id = c.elective_basket_id
LEFT JOIN LATERAL (
    SELECT sy.id,
           sy.status,
           sy.doc_type,
           sy.document,
           sy.objectives,
           sy.practical_components,
           sy.dean_edited_at,
           -- WHICH units exist, so the checklist can tick them one by one. A theory
           -- syllabus is now written and saved a unit at a time, so "four units" and
           -- "units I, II, IV, V" are different facts, and the Board needs the second.
           (SELECT coalesce(
                     array_agg(u.unit_number ORDER BY u.unit_number), ARRAY[]::int[])
              FROM syllabus_units u
             WHERE u.syllabus_id = sy.id)                         AS present_units,
           (SELECT count(*) FROM syllabus_references r
             WHERE r.syllabus_id = sy.id)                         AS reference_count,
           -- The Board's ACADEMIC STRUCTURE: how many units it asked for (4 or 5), and
           -- the hours it allocated to each. Compared against how many units the
           -- syllabus actually HAS — comparing that to a hardcoded five would flag
           -- every four-unit syllabus the Board deliberately chose.
           sy.unit_count                                         AS expected_units,
           sy.unit_hours,
           (SELECT count(*) FROM course_outcomes co
             WHERE co.syllabus_id = sy.id)                       AS outcome_count,
           (SELECT count(*) FROM syllabus_units u
             WHERE u.syllabus_id = sy.id)                        AS unit_count,
           -- Units too thin to publish. A unit with fewer topics than the floor is
           -- an outline, and it is the one defect a Board reliably misses: the
           -- document LOOKS finished, so nobody opens Unit IV to count.
           (SELECT coalesce(
                     array_agg(u.unit_number ORDER BY u.unit_number), ARRAY[]::int[])
              FROM syllabus_units u
             WHERE u.syllabus_id = sy.id
               AND jsonb_array_length(coalesce(u.topics, '[]'::jsonb)) < :weak)
                                                                 AS weak_units,
           (SELECT count(*) FROM syllabus_references r
             WHERE r.syllabus_id = sy.id
               AND r.ref_type = 'TEXTBOOK')                      AS textbook_count,
           (SELECT count(*) FROM syllabus_references r
             WHERE r.syllabus_id = sy.id
               AND r.ref_type IN ('REFERENCE', 'JOURNAL'))       AS refbook_count
    FROM syllabi sy
    WHERE sy.course_id = c.id
    ORDER BY sy.version DESC
    LIMIT 1
) s ON true
WHERE c.program_id = :p
ORDER BY c.semester, c.is_elective, c.code
"""


# ---------------------------------------------------------------------------
# The Dean's pre-submission checklist
#
# Submitting is irreversible: the Dean hands the curriculum over and never gets it
# back. A one-line error toast after the fact is the wrong shape for that — it
# tells you that you failed, not what to finish. So everything the Dean must do is
# shown as a checklist BEFORE the act, each line pointing at the section that
# fixes it.
#
# The rules are not restated here. They are read out of the same compliance engine
# that `submit_for_approval` enforces (m01/compliance.py), grouped into lines a
# Dean can act on. If the two ever disagreed, the checklist would say "ready" and
# the submit would refuse — so it is deliberately impossible for them to.
# ---------------------------------------------------------------------------

# Which compliance rule feeds which checklist line, and where the Dean fixes it.
_CHECK_GROUPS: list[tuple[str, str, str, tuple[str, ...]]] = [
    # (key, label, section, compliance rule_id prefixes)
    ("credits",   "Total credits match the programme requirement", "structure",  ("UGC-CRED-",)),
    ("semesters", "Every semester satisfies its credit rules",     "structure",  ("UGC-SEM-",)),
    ("electives", "Every elective basket is valid",                "electives",  ("UGC-ELEC-",)),
    ("codes",     "No duplicate course codes",                     "structure",  ("UGC-CODE-",)),
    ("courses",   "Every mandatory subject exists",                "structure",
     ("UGC-COURSE-", "UGC-LAB-", "UGC-FINALSEM-", "UGC-LAYOUT-", "UGC-DAG-")),
    ("outcomes",  "Programme outcomes are defined",                "outcomes",   ("UGC-PO-",)),
]


async def get_submission_checklist(
    program_id: UUID,
    db: AsyncSession,
) -> SubmissionChecklist:
    """What the Dean still has to finish before the curriculum can be handed over."""
    from app.modules.m01_program_advisor.service import ProgramService

    program = await _get_program(program_id, db)
    result = await ProgramService.run_compliance(program_id, db=db)

    # Group the compliance violations by the checklist line they belong to.
    by_key: dict[str, list] = {key: [] for key, _, _, _ in _CHECK_GROUPS}
    unmatched: list = []
    for violation in result.violations:
        for key, _, _, prefixes in _CHECK_GROUPS:
            if violation.rule_id.startswith(prefixes):
                by_key[key].append(violation)
                break
        else:
            unmatched.append(violation)

    # Which semesters actually have subjects in them.
    #
    # This is checked here rather than left to the compliance engine because the
    # engine iterates over the semesters it FINDS — so an empty semester (or an
    # empty curriculum) produces no violations at all, and every structural line
    # would pass vacuously. A Dean who had built nothing would be shown a wall of
    # green ticks and then be refused at the door. The engine is right to work that
    # way (it grades what exists); the checklist has to notice what does not.
    expected_semesters = (program.duration_years or 0) * 2
    populated = {
        row[0]
        for row in (
            await db.execute(
                text("SELECT DISTINCT semester FROM courses WHERE program_id = :p"),
                {"p": str(program_id)},
            )
        ).fetchall()
    }
    empty_semesters = [s for s in range(1, expected_semesters + 1) if s not in populated]

    items: list[SubmissionCheckItem] = [
        SubmissionCheckItem(
            key="academic_year",
            label="Academic Year selected",
            passed=bool(program.academic_year),
            blocking=True,
            detail=(
                None if program.academic_year
                else "An approved curriculum is immutable, and students stay on the "
                     "version they were admitted under — so it must know which years "
                     "it governs before it is frozen."
            ),
            section="settings",
        ),
        SubmissionCheckItem(
            key="batch",
            label="Applicable Batch selected",
            passed=program.effective_from_batch_id is not None,
            blocking=True,
            detail=(
                None if program.effective_from_batch_id
                else "Pick the first batch this curriculum version governs. Earlier "
                     "batches stay on the version they were admitted under."
            ),
            section="settings",
        ),
    ]

    for key, label, section, _ in _CHECK_GROUPS:
        violations = by_key[key]
        blockers = [v.message for v in violations if v.severity == "ERROR"]

        # An empty semester is a missing subject, and it is the single most likely
        # thing for a Dean to have left undone — so it is named, semester by
        # semester, rather than hidden behind a generic "compliance failed".
        if key == "courses" and empty_semesters:
            listed = ", ".join(str(s) for s in empty_semesters[:4])
            more = f" and {len(empty_semesters) - 4} more" if len(empty_semesters) > 4 else ""
            blockers.insert(
                0,
                f"Semester {listed}{more} "
                f"{'has' if len(empty_semesters) == 1 else 'have'} no subjects",
            )

        # A WARNING never stops the handover — it is soft advice, and the Board
        # will see it too. So a blocking line shows ONLY what is blocking it:
        # burying "Semester 4 has no subjects" in three paragraphs about missing
        # lab courses is how a Dean misses the thing they actually have to fix.
        warnings = [v.message for v in violations if v.severity != "ERROR"]
        shown = blockers or warnings

        items.append(
            SubmissionCheckItem(
                key=key,
                label=label,
                passed=not blockers,
                blocking=bool(blockers),
                detail="; ".join(shown[:3]) or None,
                section=section,
            )
        )

    if unmatched:
        errors = [v for v in unmatched if v.severity == "ERROR"]
        items.append(
            SubmissionCheckItem(
                key="compliance",
                label="Programme compliance passes",
                passed=not errors,
                blocking=bool(errors),
                detail="; ".join(v.message for v in (errors or unmatched)[:3]) or None,
                section="compliance",
            )
        )

    blocked = [i for i in items if i.blocking and not i.passed]
    return SubmissionChecklist(
        program_id=program_id,
        can_submit=not blocked,
        items=items,
        first_failing_section=blocked[0].section if blocked else None,
    )


# ---------------------------------------------------------------------------
# Dean -> Board: submit
# ---------------------------------------------------------------------------

async def submit_for_approval(
    program_id: UUID,
    submitted_by: UUID,
    note: str | None,
    *,
    db: AsyncSession,
) -> UUID:
    """DRAFT -> PENDING_APPROVAL. A one-way handover.

    The Dean hands the academic plan to the Board. From this moment the Dean is
    read-only on this curriculum version — permanently. There is no return path;
    the Board will enhance whatever needs enhancing itself.

    Compliance is checked here, at the handover — the Board should never be asked
    to review a curriculum that fails the institution's own credit rules.

    A curriculum must know which batch it governs before it is submitted: the
    approved version is immutable and students stay on the version they were
    admitted under, so "which batch is this?" cannot be answered later.
    """
    program = await _get_program(program_id, db)
    if program.status != ProgramStatus.DRAFT.value:
        raise GovernanceServiceError(
            "INVALID_STATUS",
            f"Only a Draft curriculum can be submitted; this one is {program.status}.",
            409,
        )

    # Compliance first, then the batch binding. Both must hold, but a Dean with a
    # half-built curriculum and no batch set should be told about the curriculum:
    # the missing batch is a thirty-second fix, the credit structure is not, and
    # leading with the trivial complaint buries the real one.
    #
    # Reuse m01's compliance engine — one definition of a valid curriculum.
    from app.modules.m01_program_advisor.service import ProgramService

    result = await ProgramService.run_compliance(program_id, db=db)
    if not result.passed:
        errors = "; ".join(v.message for v in result.violations if v.severity == "ERROR")
        raise GovernanceServiceError(
            "COMPLIANCE_FAILED",
            f"Curriculum does not satisfy compliance rules: {errors}",
            422,
        )

    # An empty semester is a missing subject. The compliance engine grades the
    # semesters it FINDS, so it says nothing about one that does not exist — which
    # would let a curriculum with a hole in it reach the Board. Checked here so
    # that this and `get_submission_checklist` can never disagree: a checklist that
    # blocks what the API would accept (or vice versa) is worse than no checklist.
    expected_semesters = (program.duration_years or 0) * 2
    populated = {
        row[0]
        for row in (
            await db.execute(
                text("SELECT DISTINCT semester FROM courses WHERE program_id = :p"),
                {"p": str(program_id)},
            )
        ).fetchall()
    }
    empty = [s for s in range(1, expected_semesters + 1) if s not in populated]
    if empty:
        listed = ", ".join(str(s) for s in empty)
        raise GovernanceServiceError(
            "SEMESTER_EMPTY",
            f"Semester {listed} {'has' if len(empty) == 1 else 'have'} no subjects. "
            "Every semester must be populated before the curriculum is handed over.",
            422,
        )

    if not program.academic_year or not program.effective_from_batch_id:
        raise GovernanceServiceError(
            "BATCH_REQUIRED",
            "Set the Academic Year and the Batch this curriculum governs before "
            "submitting. An approved curriculum is immutable, and students remain "
            "on the version they were admitted under — so it must know its batch.",
            422,
        )

    if await _open_request(program_id, db) is not None:
        raise GovernanceServiceError(
            "ALREADY_SUBMITTED",
            "This curriculum is already with the governance authority.",
            409,
        )

    request_id = uuid4()
    await db.execute(
        text(
            "INSERT INTO curriculum_approval_requests "
            "(id, program_id, cycle, status, submitted_by_user_id, submission_note) "
            "VALUES (:id, :p, 1, 'PENDING', :u, :n)"
        ),
        {"id": str(request_id), "p": str(program_id), "u": str(submitted_by), "n": note},
    )
    await db.execute(
        text(
            "UPDATE programs SET status = :s, submitted_by_user_id = :u, "
            "submitted_at = now(), updated_at = now() WHERE id = :p"
        ),
        {"s": ProgramStatus.PENDING_APPROVAL.value, "u": str(submitted_by), "p": str(program_id)},
    )
    await _commit(db, program_id)
    return request_id


# ---------------------------------------------------------------------------
# Board -> readiness: what is left before this can be approved
# ---------------------------------------------------------------------------

# The document sections each type must have filled before it is worth approving.
# Keyed to the same field names the AI writes and the Board edits
# (m02.schemas.DOCUMENT_SCHEMAS), so a section renamed there fails loudly here
# rather than silently stopping being checked.
#
# `duration` and `credits` are scalars, not lists, and are checked separately.
_REQUIRED_DOC_SECTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    CourseType.LAB.value: (
        ("experiments",           "Experiment List"),
        ("equipment",             "Equipment / Software"),
        ("assessment_guidelines", "Assessment Guidelines"),
    ),
    CourseType.INTERNSHIP.value: (
        ("guidelines",           "Internship Guidelines"),
        ("evaluation_rubric",    "Evaluation Rubric"),
        ("weekly_activities",    "Weekly Activities"),
        ("company_requirements", "Company Requirements"),
        ("report_format",        "Report Format"),
        ("viva_guidelines",      "Viva Guidelines"),
    ),
    CourseType.MINI_PROJECT.value: (
        ("guidelines",   "Project Guidelines"),
        ("milestones",   "Milestones"),
        ("deliverables", "Deliverables"),
        ("reviews",      "Reviews"),
        ("rubrics",      "Rubrics"),
    ),
    CourseType.MAJOR_PROJECT.value: (
        ("handbook",            "Project Handbook"),
        ("proposal_format",     "Proposal Format"),
        ("timeline",            "Timeline"),
        ("reviews",             "Reviews"),
        ("rubrics",             "Rubrics"),
        ("final_report_format", "Final Report Format"),
        ("demonstration",       "Demonstration"),
        ("viva",                "Viva"),
    ),
    CourseType.SEMINAR.value: (
        ("guidelines",          "Seminar Guidelines"),
        ("topic_selection",     "Topic Selection"),
        ("presentation_format", "Presentation Format"),
        ("evaluation_rubric",   "Evaluation Rubric"),
        ("deliverables",        "Deliverables"),
    ),
}

_THEORY_UNITS = 5
_MIN_OUTCOMES = 4


# ---------------------------------------------------------------------------
# The readiness checklist — the academic lifecycle of ONE document
#
# What the Board sees is a stage of the workflow, never a rule of the machine. Not
# "Unit III has 2 topics; a unit runs to 10-15", not "validation threshold", not
# "attempt 2 of 3" — those are ours, they live in the backend, and a Board member who
# reads them learns only that we do not trust our own generator. What they see is:
#
#     ✓ Unit III        it is written, and it is deep enough to print
#     ⚠ Unit IV         AI generation incomplete — regenerate it
#       Unit V          not written yet
#
# THREE shapes, because there are three kinds of document and forcing one shape on all
# of them is what produced a lab manual asked for its Unit III:
#
#     THEORY      structure -> draft -> Unit I..N -> objectives -> outcomes ->
#                 references -> Board approved -> published
#     LAB         structure -> draft -> lab manual -> outcomes -> references ->
#                 Board approved -> published      (a laboratory has no units)
#     EXECUTION   created -> draft -> Dean reviewed -> Dean approved -> published
#                 (the Board is not in this list at all — it does not own them)
# ---------------------------------------------------------------------------

_DONE       = "DONE"
_PENDING    = "PENDING"
_INCOMPLETE = "INCOMPLETE"    # exists, but the AI did not finish it


def _item(key: str, label: str, state: str, **extra) -> ChecklistItem:
    return ChecklistItem(key=key, label=label, state=state, **extra)


def _tick(done: bool, key: str, label: str) -> ChecklistItem:
    return _item(key, label, _DONE if done else _PENDING)


def _build_checklist(row, published: bool) -> list[ChecklistItem]:
    """The lifecycle of this document, as an academic would describe it."""
    doc_type = normalize_course_type(row.doc_type or row.course_type)
    status   = row.syllabus_status
    exists   = row.syllabus_id is not None
    approved = status in ("APPROVED", "LOCKED")

    if is_execution_document(doc_type):
        return _execution_checklist(row, exists, approved, published)

    return _teaching_checklist(row, doc_type, exists, approved, published)


def _teaching_checklist(row, doc_type, exists, approved, published) -> list[ChecklistItem]:
    """A subject the Board teaches. Two shapes, because there are two kinds.

    THEORY   Structure -> Unit I..N -> Objectives -> Outcomes -> References ->
             Board Approval -> Published
    LAB      Structure -> Lab Manual -> Experiments -> Outcomes -> References ->
             Board Approval -> Published

    A laboratory has no Unit III and never had. Asking it for one is the mistake course
    types exist to prevent, and it would reappear here the moment one checklist was
    made to serve both.
    """
    # THE ACADEMIC STRUCTURE — the Board's decisions, taken before any AI ran: how many
    # units the subject is taught in, and for how long each. It is the FIRST stage
    # because it is the first thing that has to happen, and because a syllabus cannot be
    # generated without it — the system does not derive it and the model never picks it.
    #
    # A laboratory has no units, so its structure is the curriculum's own: the course,
    # its credits, its practical hours. Nothing further is required of the Board.
    if doc_type == CourseType.THEORY.value:
        structure_set = bool(row.expected_units) and bool(exists) and (
            len(row.unit_hours or []) == (row.expected_units or 0)
        )
        items = [_tick(structure_set, "structure", "Academic Structure")]

        present  = set(row.present_units or [])
        weak     = set(row.weak_units or [])
        expected = row.expected_units or _THEORY_UNITS

        for number in range(1, expected + 1):
            if number not in present:
                state = _PENDING
            elif number in weak:
                state = _INCOMPLETE      # written, but the AI did not finish it
            else:
                state = _DONE
            items.append(_item(
                f"unit_{number}", f"Unit {roman(number)}", state, unit_number=number,
            ))
    else:
        document = row.document or {}
        items = [_item("structure", "Academic Structure", _DONE)]
        # The manual is the laboratory's document: what it is for, what it needs to run.
        # The experiments are what the student actually performs in the room. A manual
        # with no experiment list is a laboratory nobody can teach.
        items.append(_tick(bool(document), "lab_manual", "Lab Manual"))
        items.append(_tick(
            len(document.get("experiments") or []) > 0, "experiments", "Experiments",
        ))

    # Objectives are theory's; a laboratory's document carries its own aims. Outcomes
    # are BOTH — a lab has Lab Outcomes, they map to Programme Outcomes like any other,
    # and approval will not pass without them. Showing a stage the gate tests is the
    # entire point of a checklist.
    if doc_type == CourseType.THEORY.value:
        items.append(_tick(bool(row.objectives or []), "objectives", "Objectives"))

    items.append(_tick((row.outcome_count or 0) >= _MIN_OUTCOMES, "outcomes", "Outcomes"))

    # ADVISORY, and said so. The references come from CrossRef and OpenLibrary, and a
    # third-party outage must never be able to block a university's curriculum. It is
    # the ONE stage on any checklist that the approval gate does not test, and it is
    # marked optional so the Board is never told something is required when it is not.
    items.append(_item(
        "references",
        "References (optional)",
        _DONE if (row.reference_count or 0) > 0 else _PENDING,
        optional=True,
    ))

    items.append(_tick(approved, "approved", "Board Approval"))
    items.append(_tick(published, "published", "Published"))

    return items


def _execution_checklist(row, exists, approved, published) -> list[ChecklistItem]:
    """The Dean's document. The Board appears nowhere in it, because it owns none of it.

    "Dean Reviewed" is DERIVED — he has either adapted the document to this institution
    (dean_edited_at) or signed it off. It is not a button, and it should not be: a
    review step that records nothing except that somebody clicked it is a ceremony, and
    the approval below it already carries his name.
    """
    return [
        _tick(exists, "created", "Document Created"),
        _tick(exists and bool(row.document or {}), "draft", "AI Draft Generated"),
        _tick(bool(row.dean_edited_at) or approved, "reviewed", "Dean Reviewed"),
        _tick(approved, "approved", "Dean Approved"),
        _tick(published, "published", "Published"),
    ]


def _percent(items: list[ChecklistItem]) -> int:
    """How far along this document is, against ITS OWN checklist.

    A theory syllabus is measured against units, objectives, outcomes and approval; an
    internship against the Dean's four steps. Measuring both against one denominator
    would make an internship look 40% finished the moment it was created.

    OPTIONAL stages are excluded from the denominator. Only the References are optional,
    and they are the one stage the approval gate does not test — so counting them would
    mean a syllabus that is ready to approve could never read 100%, and the Board would
    learn to distrust the number.
    """
    required = [i for i in items if not i.optional]
    if not required:
        return 0
    done = sum(1 for i in required if i.state == _DONE)
    return round(done * 100 / len(required))


def _readiness_gaps(row) -> list[str]:
    """What is still wrong with this subject's official document, and what to DO.

    The Board's real problem is not the subject with NO syllabus — that one is
    obvious, and the dashboard already shows it. It is the subject whose document
    exists, looks complete, and is quietly hollow: Unit IV has three topics, or the
    Reference Books never came back from CrossRef. Nobody re-opens an approved-
    looking document to count its topics, so this counts them.

    Each line names the ACTION, not the diagnosis. "Unit IV has only 2 topics; an
    official unit runs to 10-15" describes the defect accurately and leaves the reader
    to work out that a button exists and which one it is. A Board member reading a
    worksheet of forty subjects wants to know what to click.

    Returns [] when the document has nothing missing. What is CHECKED depends on the
    course's type: a lab manual is not missing its Unit III.
    """
    if row.syllabus_id is None:
        return []                       # no document at all — the caller says so

    gaps: list[str] = []
    doc_type = normalize_course_type(row.doc_type or row.course_type)
    document = row.document or {}

    if not (row.objectives or []):
        gaps.append("Missing: Course Objectives")
    if (row.outcome_count or 0) < _MIN_OUTCOMES:
        gaps.append(f"Only {row.outcome_count or 0} Course Outcomes")

    if doc_type == CourseType.THEORY.value:
        # What the Board ASKED for, not a hardcoded five. A four-unit syllabus is a
        # four-unit syllabus, and flagging it as short of an "official format" it was
        # never written to is how a dashboard teaches people to ignore it.
        expected = row.expected_units or _THEORY_UNITS
        actual = row.unit_count or 0

        if actual == 0:
            gaps.append("AI generation incomplete — regenerate this syllabus")
        elif actual != expected:
            gaps.append(f"{actual} units, but this syllabus was written for {expected}")

        # The thin unit: the defect the Board cannot see without counting, because the
        # document LOOKS finished. One line, naming the units and the button.
        weak = list(row.weak_units or [])
        if weak:
            units = ", ".join(f"Unit {roman(n)}" for n in weak)
            gaps.append(f"AI generation incomplete — regenerate {units}")

        if not (row.textbook_count or 0):
            gaps.append("Missing: Text Books")
        if not (row.refbook_count or 0):
            gaps.append("Missing: Reference Books")

        # A course with practical hours whose syllabus carries no practical
        # components promises a laboratory that the document never describes.
        if (row.hours_practical or 0) > 0 and not (row.practical_components or []):
            gaps.append("Missing: Practical Components")

    else:
        for field, label in _REQUIRED_DOC_SECTIONS.get(doc_type, ()):
            if not document.get(field):
                gaps.append(f"Missing: {label}")

        # A lab manual with equipment but no software is fine, and vice versa — the
        # requirement is that it names SOMETHING it needs to run. The loop above
        # would otherwise flag every software-only laboratory.
        if doc_type == CourseType.LAB.value and (
            document.get("equipment") or document.get("software")
        ):
            gaps = [g for g in gaps if g != "Missing: Equipment / Software"]

        if doc_type == CourseType.INTERNSHIP.value and not document.get("duration"):
            gaps.append("Missing: Duration")

    return gaps


async def get_readiness(program_id: UUID, db: AsyncSession) -> ReadinessSummary:
    """Per-subject syllabus state — the Board's working surface, and the exact
    thing the approve gate tests. `can_approve` here and the gate in
    `approve_and_lock` read the same rows, so the button and the API can never
    disagree about whether a curriculum is ready.

    `gaps` is advisory and does NOT feed `can_approve`. A Board may knowingly
    approve a syllabus with no web resources, and the gate would be intolerable if a
    missing suggested-reading list could block an entire curriculum. The gate tests
    what it has always tested: that every subject's document has been APPROVED by a
    human. The gaps tell that human what to look at first.
    """
    program = await _get_program(program_id, db)
    rows = (
        await db.execute(
            text(_ALL_SUBJECTS_SQL),
            {"p": str(program_id), "weak": MIN_TOPICS_PER_UNIT},
        )
    ).fetchall()

    # The last stage of every checklist. A document is published when its CURRICULUM is
    # — there is no per-document publish, and inventing one would be inventing a second
    # answer to "is this official?".
    published = program.status == ProgramStatus.PUBLISHED

    items = [
        ReadinessItem(
            course_id=r.course_id,
            course_code=r.code,
            course_title=r.title,
            semester=r.semester,
            is_elective=r.is_elective,
            basket_name=r.basket_name,
            syllabus_id=r.syllabus_id,
            syllabus_status=r.syllabus_status,
            course_type=normalize_course_type(r.doc_type or r.course_type),
            # WHO owns this document. The Board teaches, examines and owns the syllabus
            # of theory subjects, laboratories and elective options. An internship, a
            # project and a seminar are the Dean's: what they contain depends on the
            # host company, the supervisor and the review calendar, none of which a
            # Board of Studies can know. They are listed here so the Board can SEE the
            # curriculum whole — and they carry no gaps, no actions and no weight in
            # the gate below.
            owner="DEAN" if is_execution_document(r.doc_type or r.course_type) else "BOARD",
            gaps=[] if is_execution_document(r.doc_type or r.course_type) else _readiness_gaps(r),
            checklist=_build_checklist(r, published),
            progress_percent=_percent(_build_checklist(r, published)),
        )
        for r in rows
    ]

    # The gate counts the subjects the Board OWNS. An internship document that the Dean
    # has not written yet cannot block a curriculum the Board is finished with — that
    # was the deadlock: a Board of Studies unable to approve its own curriculum until
    # somebody signed off the evaluation rubric of an internship nobody had arranged.
    taught = [i for i in items if i.owner == "BOARD"]
    dean   = [i for i in items if i.owner == "DEAN"]

    approved = sum(1 for i in taught if i.syllabus_status in ("APPROVED", "LOCKED"))
    drafted  = sum(1 for i in taught if i.syllabus_status in ("DRAFT", "AI_GENERATING"))
    missing  = [i for i in taught if i.syllabus_status is None]

    # Two figures, and neither waits on the other. A Board at 95% and a Dean at 60% are
    # two true statements about two bodies doing different work — one combined number
    # would be a lie about both.
    board_percent = (
        round(sum(i.progress_percent for i in taught) / len(taught)) if taught else 0
    )
    dean_percent = (
        round(sum(i.progress_percent for i in dean) / len(dean)) if dean else 100
    )

    # THE SECOND GATE — the Dean's. He publishes when the Board has finished its half
    # AND every document of his own is approved. Publishing a curriculum whose internship
    # nobody has written would release to students a programme with a component that does
    # not exist, and they would find out in their final year.
    #
    # Read from the same rows m01.publish tests, so the button and the endpoint cannot
    # disagree — the same discipline as `can_approve`.
    dean_approved = sum(1 for i in dean if i.syllabus_status in ("APPROVED", "LOCKED"))
    board_finished = program.status in (ProgramStatus.APPROVED, ProgramStatus.PUBLISHED)
    can_publish = board_finished and dean_approved == len(dean)

    return ReadinessSummary(
        program_id=program_id,
        total_subjects=len(taught),
        approved_count=approved,
        draft_count=drafted,
        board_progress_percent=board_percent,
        dean_progress_percent=dean_percent,
        dean_document_count=len(dean),
        dean_approved_count=dean_approved,
        can_publish=can_publish,
        missing_count=len(missing),
        can_approve=bool(taught) and approved == len(taught),
        items=items,
    )


# ---------------------------------------------------------------------------
# Board -> approve + lock
# ---------------------------------------------------------------------------

async def approve_and_lock(
    program_id: UUID,
    decided_by: UUID,
    comment: str | None,
    *,
    db: AsyncSession,
) -> int:
    """PENDING_APPROVAL -> APPROVED (locked). The only freeze, and it is final.

    Refuses unless every subject has an APPROVED syllabus (see module docstring).
    Without that gate a curriculum could be locked with no syllabus at all, and
    since locked means locked, the only repair would be a whole new version.

    Locks, in one transaction: the program, every syllabus hanging off its
    courses, and every elective basket's composition. After this nobody edits —
    not the Dean, not the Board, not Faculty, not Admin.

    Returns the number of syllabi locked.
    """
    program = await _require_program_status(program_id, ProgramStatus.PENDING_APPROVAL, db)

    request = await _open_request(program_id, db)
    if request is None:
        raise GovernanceServiceError(
            "NO_OPEN_REQUEST",
            "There is no open approval request for this curriculum.",
            409,
        )

    # There is deliberately NO separation of duties inside the Board.
    #
    # One member may receive a curriculum, enhance it, generate and edit the
    # official syllabus, approve it and lock it — alone. That is not a gap; it is
    # the model. The Board is ONE academic authority, not a ladder of approval
    # levels, and its members are equal peers. Requiring a second pair of eyes
    # would invent a hierarchy the institution does not have, and would stall a
    # curriculum whenever only one member was available.
    #
    # Accountability comes from the record instead of from a restriction: every
    # review, modification, syllabus generation, syllabus approval and curriculum
    # approval is written to the append-only audit log with its actor, role and
    # timestamp, and is readable as a governance trail (`get_audit_trail`). Who
    # did what is never in doubt — it simply is not used to forbid anything.
    #
    # The ONE person who can never approve is the Dean, and that rule lives in
    # `acts_as_governance`: the planner must not approve their own plan.

    # The gate. Every TEACHING subject — core and every elective option — needs an
    # approved official syllabus before the curriculum can be frozen.
    #
    # The Dean's execution documents are not in this gate, and must not be. An
    # internship is arranged with a company months after a curriculum is approved; a
    # Board of Studies that had to wait for its rubric would never approve anything.
    # `get_readiness` already counts only what the Board owns — this reads the same
    # rows, so the button and the gate can never disagree.
    readiness = await get_readiness(program_id, db)
    if not readiness.can_approve:
        unready = [
            f"{i.course_code} {i.course_title}"
            + ("" if i.syllabus_status is None else f" ({i.syllabus_status.lower()})")
            for i in readiness.items
            if i.owner == "BOARD" and i.syllabus_status not in ("APPROVED", "LOCKED")
        ]
        detail = "; ".join(unready[:10])
        if len(unready) > 10:
            detail += f"; and {len(unready) - 10} more"
        raise GovernanceServiceError(
            "SYLLABUS_INCOMPLETE",
            "Every teaching subject must have an approved official syllabus before the "
            "curriculum can be approved. Approval is permanent, so a subject "
            f"locked without a syllabus could never be given one. Outstanding: {detail}",
            422,
        )

    from app.modules.m01_program_advisor.service import ProgramService

    result = await ProgramService.run_compliance(program_id, db=db)
    if not result.passed:
        errors = "; ".join(v.message for v in result.violations if v.severity == "ERROR")
        raise GovernanceServiceError("COMPLIANCE_FAILED", errors, 422)

    await db.execute(
        text(
            "UPDATE curriculum_approval_requests SET status = 'APPROVED', "
            "decided_by_user_id = :u, decided_at = now(), decision_comment = :c "
            "WHERE id = :id"
        ),
        {"u": str(decided_by), "c": comment, "id": str(request.id)},
    )
    await db.execute(
        text(
            "UPDATE programs SET status = :s, approved_by_user_id = :u, approved_at = now(), "
            "locked_by_user_id = :u, locked_at = now(), review_comment = :c, updated_at = now() "
            "WHERE id = :p"
        ),
        {
            "s": ProgramStatus.APPROVED.value,
            "u": str(decided_by),
            "c": comment,
            "p": str(program_id),
        },
    )

    # Freeze the TAUGHT syllabi with the curriculum — the theory subjects, the
    # laboratories, the elective options. Those are the Board's, the Board has approved
    # them, and nothing inside a locked curriculum ever changes again.
    #
    # The Dean's execution documents are NOT frozen here. He has not written them yet:
    # an internship is arranged with a company long after the curriculum is approved,
    # and locking its empty guidelines at the moment of approval would leave a document
    # that can never be written, for a student who must nevertheless be assessed against
    # it. He owns them, he approves them, and he publishes them.
    locked = await db.execute(
        text(
            "UPDATE syllabi SET status = 'LOCKED', locked_by_user_id = :u, "
            "locked_at = now(), updated_at = now() "
            "WHERE course_id IN (SELECT id FROM courses WHERE program_id = :p) "
            "AND status <> 'LOCKED' "
            "AND doc_type NOT IN :execution "
            "RETURNING id"
        ).bindparams(bindparam("execution", expanding=True)),
        {
            "u": str(decided_by),
            "p": str(program_id),
            "execution": sorted(EXECUTION_TYPES),
        },
    )
    locked_count = len(locked.fetchall())

    # Freeze the elective baskets' COMPOSITION. Their registration lifecycle
    # (ElectiveSlotStatus) keeps moving — the Dean still opens and closes student
    # choice each year on a published curriculum. What can never change again is
    # WHICH subjects the basket offers.
    await db.execute(
        text(
            "UPDATE elective_baskets SET locked_at = now(), locked_by_user_id = :u, "
            "updated_at = now() WHERE program_id = :p AND locked_at IS NULL"
        ),
        {"u": str(decided_by), "p": str(program_id)},
    )

    await _commit(db, program_id)
    logger.info(
        "curriculum_approved program=%s version=%s syllabi_locked=%s",
        program_id, program.version, locked_count,
    )
    return locked_count


# ---------------------------------------------------------------------------
# Reads — queue, change summary, history
# ---------------------------------------------------------------------------

_QUEUE_SQL = """
SELECT p.id, p.title, p.department, p.degree_type, p.version, p.status,
       p.total_credits, p.duration_years, p.regulation_year, p.academic_year,
       p.submitted_at, p.locked_at, p.published_at,
       su.full_name AS submitted_by_name,
       car.submission_note,
       b.name AS batch_name,
       (SELECT count(*) FROM courses c WHERE c.program_id = p.id)                AS course_count,
       (SELECT count(*) FROM elective_baskets eb WHERE eb.program_id = p.id)     AS elective_slot_count,
       -- The Board's counters count the Board's WORK: the taught curriculum.
       --
       -- An internship's guidelines belong to the Dean, and a queue that counted them
       -- would show a Board of Studies "8 of 10 syllabi approved" when it had in fact
       -- finished — the two it was still waiting on being documents it does not own,
       -- cannot write, and must not be asked about.
       (SELECT count(*) FROM syllabi s
          JOIN courses c ON c.id = s.course_id
         WHERE c.program_id = p.id
           AND coalesce(s.doc_type, 'THEORY') NOT IN ('INTERNSHIP', 'MINI_PROJECT',
                                                      'MAJOR_PROJECT', 'SEMINAR'))  AS syllabus_count,
       (SELECT count(*) FROM syllabi s
          JOIN courses c ON c.id = s.course_id
         WHERE c.program_id = p.id
           AND coalesce(s.doc_type, 'THEORY') NOT IN ('INTERNSHIP', 'MINI_PROJECT',
                                                      'MAJOR_PROJECT', 'SEMINAR')
           AND s.status IN ('APPROVED', 'LOCKED'))                                  AS approved_syllabus_count
FROM programs p
LEFT JOIN users su ON su.id = p.submitted_by_user_id
LEFT JOIN acad_batches b ON b.id = p.effective_from_batch_id
LEFT JOIN curriculum_approval_requests car
       ON car.program_id = p.id AND car.status = 'PENDING'
WHERE p.status = ANY(:statuses)
ORDER BY COALESCE(p.submitted_at, p.created_at) DESC
"""


def _to_item(row) -> QueueItem:
    return QueueItem(
        program_id=row.id,
        title=row.title,
        department=row.department,
        degree_type=row.degree_type,
        version=row.version,
        status=row.status,
        total_credits=row.total_credits,
        duration_years=row.duration_years,
        regulation_year=row.regulation_year,
        academic_year=row.academic_year,
        batch_name=row.batch_name,
        course_count=row.course_count,
        elective_slot_count=row.elective_slot_count,
        syllabus_count=row.syllabus_count,
        approved_syllabus_count=row.approved_syllabus_count,
        submitted_at=row.submitted_at,
        submitted_by_name=row.submitted_by_name,
        submission_note=row.submission_note,
        locked_at=row.locked_at,
        published_at=row.published_at,
    )


async def get_queue(db: AsyncSession) -> dict[str, list[QueueItem]]:
    async def _fetch(statuses: list[str]) -> list[QueueItem]:
        rows = (await db.execute(text(_QUEUE_SQL), {"statuses": statuses})).fetchall()
        return [_to_item(r) for r in rows]

    return {
        "pending":   await _fetch([ProgramStatus.PENDING_APPROVAL.value]),
        "approved":  await _fetch([ProgramStatus.APPROVED.value]),
        "published": await _fetch([ProgramStatus.PUBLISHED.value]),
    }


# What the Dean is shown after the Board finalizes their curriculum. Each event
# the Board raised while it held the curriculum becomes one plain-English line.
#
# This is read out of the EXISTING audit log rather than a bespoke table: the
# audit log already records actor_role, event_type, a JSONB metadata blob and a
# timestamp, and is already append-only by project rule. A second ledger would
# have added a table to keep in sync for no information we do not already have.
_CHANGE_EVENTS: dict[str, str] = {
    "PROGRAM_UPDATED":              "Revised programme details",
    "PROGRAM_COURSE_ADDED":         "Added subject",
    "PROGRAM_COURSE_UPDATED":       "Updated subject",
    "PROGRAM_COURSE_DELETED":       "Removed subject",
    "PROGRAM_OUTCOME_ADDED":        "Added programme outcome",
    "PROGRAM_OUTCOME_UPDATED":      "Updated programme outcome",
    "PROGRAM_OUTCOME_DELETED":      "Removed programme outcome",
    "ELECTIVE_BASKET_CREATED":      "Added elective",
    "ELECTIVE_BASKET_UPDATED":      "Updated elective",
    "ELECTIVE_BASKET_DELETED":      "Removed elective",
    "ELECTIVE_CHOICE_ADDED":        "Added elective option",
    "ELECTIVE_CHOICE_REMOVED":      "Removed elective option",
    "SYLLABUS_GENERATION_COMPLETED": "Generated official syllabus",
    "SYLLABUS_UPDATED":             "Revised official syllabus",
    "SYLLABUS_UNIT_ADDED":          "Revised official syllabus",
    "SYLLABUS_UNIT_UPDATED":        "Revised official syllabus",
    "SYLLABUS_UNIT_DELETED":        "Revised official syllabus",
    "SYLLABUS_CO_ADDED":            "Revised course outcomes",
    "SYLLABUS_CO_UPDATED":          "Revised course outcomes",
    "SYLLABUS_CO_DELETED":          "Revised course outcomes",
    "SYLLABUS_REFERENCE_ADDED":     "Revised references",
    "SYLLABUS_REFERENCE_UPDATED":   "Revised references",
    "SYLLABUS_REFERENCE_DELETED":   "Revised references",
}

_CHANGES_SQL = """
SELECT al.event_type, al.created_at, u.full_name AS actor_name
FROM public.audit_logs al
LEFT JOIN users u ON u.id = al.actor_user_id
WHERE al.tenant_id = :tenant
  AND al.metadata->>'program_id' = :program_id
  AND al.created_at >= :since
  AND al.event_type = ANY(:events)
ORDER BY al.created_at
"""


# ---------------------------------------------------------------------------
# The governance trail — who reviewed, who modified, who approved, and when
#
# The Board has no separation of duties: one member may enhance a curriculum,
# write its syllabus, and approve it alone. Accountability therefore rests
# ENTIRELY on this record, which is why it is a first-class read rather than
# something an admin has to go digging for in the raw audit table.
#
# It is assembled from the append-only audit log — no second ledger to keep in
# sync, and nothing here can be edited or deleted after the fact.
# ---------------------------------------------------------------------------

_TRAIL_EVENTS: dict[str, tuple[str, str]] = {
    # event_type                     -> (action label, category)
    "CURRICULUM_SUBMITTED":           ("Submitted the curriculum",            "SUBMIT"),
    "CURRICULUM_REVIEW_OPENED":       ("Opened the curriculum for review",    "REVIEW"),
    "PROGRAM_UPDATED":                ("Revised programme details",           "MODIFY"),
    "PROGRAM_COURSE_ADDED":           ("Added a subject",                     "MODIFY"),
    "PROGRAM_COURSE_UPDATED":         ("Updated a subject",                   "MODIFY"),
    "PROGRAM_COURSE_DELETED":         ("Removed a subject",                   "MODIFY"),
    "PROGRAM_OUTCOME_ADDED":          ("Added a programme outcome",           "MODIFY"),
    "PROGRAM_OUTCOME_UPDATED":        ("Updated a programme outcome",         "MODIFY"),
    "PROGRAM_OUTCOME_DELETED":        ("Removed a programme outcome",         "MODIFY"),
    "ELECTIVE_BASKET_CREATED":        ("Added an elective",                   "MODIFY"),
    "ELECTIVE_BASKET_UPDATED":        ("Updated an elective",                 "MODIFY"),
    "ELECTIVE_BASKET_DELETED":        ("Removed an elective",                 "MODIFY"),
    "ELECTIVE_CHOICE_ADDED":          ("Added an elective option",            "MODIFY"),
    "ELECTIVE_CHOICE_REMOVED":        ("Removed an elective option",          "MODIFY"),
    "SYLLABUS_GENERATION_QUEUED":     ("Generated the official syllabus",     "SYLLABUS"),
    "SYLLABUS_GENERATION_COMPLETED":  ("Syllabus generated",                  "SYLLABUS"),
    "SYLLABUS_UPDATED":               ("Edited a syllabus",                   "SYLLABUS"),
    "SYLLABUS_UNIT_ADDED":            ("Edited syllabus units",               "SYLLABUS"),
    "SYLLABUS_UNIT_UPDATED":          ("Edited syllabus units",               "SYLLABUS"),
    "SYLLABUS_UNIT_DELETED":          ("Edited syllabus units",               "SYLLABUS"),
    "SYLLABUS_CO_ADDED":              ("Edited course outcomes",              "SYLLABUS"),
    "SYLLABUS_CO_UPDATED":            ("Edited course outcomes",              "SYLLABUS"),
    "SYLLABUS_CO_DELETED":            ("Edited course outcomes",              "SYLLABUS"),
    "SYLLABUS_REFERENCE_ADDED":       ("Edited references",                   "SYLLABUS"),
    "SYLLABUS_REFERENCE_UPDATED":     ("Edited references",                   "SYLLABUS"),
    "SYLLABUS_REFERENCE_DELETED":     ("Edited references",                   "SYLLABUS"),
    "SYLLABUS_APPROVED":              ("Approved a subject's syllabus",       "APPROVE"),
    "CURRICULUM_APPROVED":            ("Approved the curriculum",             "APPROVE"),
    "CURRICULUM_LOCKED":              ("Locked the curriculum",               "APPROVE"),
    "PROGRAM_PUBLISHED":              ("Published the curriculum",            "PUBLISH"),
}

_TRAIL_SQL = """
SELECT al.event_type, al.actor_role, al.created_at, al.metadata,
       u.full_name AS actor_name
FROM public.audit_logs al
LEFT JOIN users u ON u.id = al.actor_user_id
WHERE al.tenant_id = :tenant
  AND al.metadata->>'program_id' = :program_id
  AND al.event_type = ANY(:events)
ORDER BY al.created_at DESC
LIMIT 500
"""


async def get_audit_trail(
    program_id: UUID,
    tenant_id: UUID | None,
    db: AsyncSession,
) -> list[TrailEntry]:
    """Every governance action on this curriculum, newest first.

    Not scoped to the Board's tenure: the Dean's own submit and publish belong on
    the record too, so the trail reads as the whole life of the curriculum.
    """
    if tenant_id is None:
        return []

    rows = (
        await db.execute(
            text(_TRAIL_SQL),
            {
                "tenant": str(tenant_id),
                "program_id": str(program_id),
                "events": list(_TRAIL_EVENTS),
            },
        )
    ).fetchall()

    entries: list[TrailEntry] = []
    for row in rows:
        label, category = _TRAIL_EVENTS[row.event_type]
        entries.append(
            TrailEntry(
                event_type=row.event_type,
                action=label,
                category=category,
                actor_name=row.actor_name,
                actor_role=row.actor_role,
                at=row.created_at,
                detail=_trail_detail(row.event_type, row.metadata or {}),
            )
        )
    return entries


def _trail_detail(event_type: str, meta: dict) -> str | None:
    """One line of context, when there is one worth showing."""
    if event_type == "SYLLABUS_GENERATION_QUEUED":
        n = meta.get("dispatched")
        return f"{n} subject{'' if n == 1 else 's'}" if n else None
    if event_type in ("PROGRAM_COURSE_ADDED", "ELECTIVE_CHOICE_ADDED"):
        return meta.get("code")
    if event_type == "CURRICULUM_LOCKED":
        n = meta.get("syllabi_locked")
        return f"{n} syllabi frozen" if n else None
    if event_type in ("CURRICULUM_APPROVED", "CURRICULUM_SUBMITTED"):
        return meta.get("comment") or meta.get("note")
    return None


async def record_review_opened(
    program_id: UUID,
    user: CurrentUser,
    db: AsyncSession,
) -> bool:
    """Note that this Board member opened the curriculum for review. Returns True
    if a new entry was written.

    "Who reviewed" is part of the record the Board is accountable to, so opening
    the worksheet has to leave a trace. But the worksheet POLLS while syllabus
    generation runs, so writing an entry on every read would bury the trail under
    thousands of identical rows in an append-only table that can never be cleaned
    up.

    So it is deduplicated: at most one entry per member per curriculum per day.
    That answers "who looked at this, and when" without the noise.
    """
    existing = (
        await db.execute(
            text(
                "SELECT 1 FROM public.audit_logs "
                "WHERE tenant_id = :t AND actor_user_id = :u "
                "  AND event_type = 'CURRICULUM_REVIEW_OPENED' "
                "  AND metadata->>'program_id' = :p "
                "  AND created_at >= date_trunc('day', now()) "
                "LIMIT 1"
            ),
            {"t": str(user.tenant_id), "u": str(user.user_id), "p": str(program_id)},
        )
    ).first()
    return existing is None


async def get_change_summary(
    program_id: UUID,
    tenant_id: UUID | None,
    db: AsyncSession,
) -> ChangeSummary:
    """What the Board did to this curriculum while it held it.

    Scoped to events raised AFTER the Dean submitted, which is precisely the
    Board's tenure over the curriculum: before that moment every change was the
    Dean's own, and the Dean does not need to be told about those.

    Grouped into counted lines — "Added subject x2" — because the Dean wants to
    know what changed, not to read an event log.
    """
    program = await _get_program(program_id, db)
    if program.submitted_at is None or tenant_id is None:
        return ChangeSummary(program_id=program_id, total_changes=0, lines=[])

    rows = (
        await db.execute(
            text(_CHANGES_SQL),
            {
                "tenant": str(tenant_id),
                "program_id": str(program_id),
                "since": program.submitted_at,
                "events": list(_CHANGE_EVENTS),
            },
        )
    ).fetchall()

    counts: dict[str, int] = {}
    for row in rows:
        label = _CHANGE_EVENTS.get(row.event_type)
        if label:
            counts[label] = counts.get(label, 0) + 1

    lines = [
        ChangeSummaryLine(label=label, count=count)
        for label, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    return ChangeSummary(
        program_id=program_id,
        total_changes=sum(counts.values()),
        lines=lines,
    )


async def get_history(program_id: UUID, db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT car.id, car.program_id, car.cycle, car.status, "
                "       car.submitted_by_user_id, car.submitted_at, car.submission_note, "
                "       car.decided_by_user_id, car.decided_at, car.decision_comment, "
                "       su.full_name AS submitted_by_name, du.full_name AS decided_by_name "
                "FROM curriculum_approval_requests car "
                "LEFT JOIN users su ON su.id = car.submitted_by_user_id "
                "LEFT JOIN users du ON du.id = car.decided_by_user_id "
                "WHERE car.program_id = :p ORDER BY car.cycle DESC"
            ),
            {"p": str(program_id)},
        )
    ).fetchall()
    return [dict(r._mapping) for r in rows]
