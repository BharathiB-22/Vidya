"""Academic Governance — HTTP surface (Phase A V2).

Route ownership
---------------
    /governance/info                          any authenticated tenant user
    /governance/queue                         Board only
    /governance/programs/{id}/readiness       Board only  (what is left before approval)
    /governance/programs/{id}/syllabus/generate  Board only  (bulk AI generation)
    /governance/programs/{id}/approve         Board only  (approve + lock, permanently)
    /governance/programs/{id}/changes         Dean, Admin, Board  (what the Board changed)
    /governance/programs/{id}/trail           Dean, Admin, Board  (who did what, when)
    /governance/programs/{id}/history         Dean, Admin, Board

`submit` lives on the program router (/programs/{id}/submit) because it is a Dean
action on a Dean-owned resource — see m01_program_advisor/router.py.

There is no `return` route and no `reject` route. The Board is the academic
authority: it enhances the curriculum rather than handing it back. See
governance/service.py.

Every Board mutation is gated by `require_governance`, which rejects a DEAN even
when they hold a BOARD grant — the planner must not approve their own plan.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.auth.dependencies import get_current_user, get_tenant_db_dep, require_roles
from app.core.auth.models import TenantRole
from app.core.auth.schemas import CurrentUser
from app.core.governance import service as gov
from app.core.governance.schemas import (
    ApprovalRequestOut,
    ApproveCurriculumRequest,
    ChangeSummary,
    PublishReadiness,
    GovernanceInfo,
    GovernanceQueueResponse,
    ReadinessSummary,
    TrailEntry,
)

router = APIRouter(tags=["governance"])

# Who may READ governance history and the change summary: the Dean who authored
# the curriculum, the Admin, the Board itself, and Faculty (who teach under it).
_HISTORY_READ = (TenantRole.ADMIN, TenantRole.DEAN, TenantRole.BOARD, TenantRole.FACULTY)


def _err(e: gov.GovernanceServiceError) -> HTTPException:
    return HTTPException(
        status_code=e.status_code,
        detail={"error": e.code, "message": e.message},
    )


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

@router.get("/info", response_model=GovernanceInfo)
async def governance_info(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GovernanceInfo:
    """What this tenant calls its governance authority. Drives every label in
    the UI — 'Board' for one university, 'University Members' for another."""
    return await gov.get_governance_info(current_user.tenant_id, db)


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

@router.get("/queue", response_model=GovernanceQueueResponse)
async def review_queue(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> GovernanceQueueResponse:
    try:
        await gov.require_governance(current_user, db)
        buckets = await gov.get_queue(db)
    except gov.GovernanceServiceError as e:
        raise _err(e)
    return GovernanceQueueResponse(**buckets)


# ---------------------------------------------------------------------------
# Readiness — the Board's worksheet
# ---------------------------------------------------------------------------

@router.get("/programs/{program_id}/readiness", response_model=ReadinessSummary)
async def curriculum_readiness(
    program_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ReadinessSummary:
    """Per-subject syllabus state, and whether the curriculum can be approved.

    Reads exactly the rows the approve gate tests, so the Approve button and the
    API can never disagree about whether a curriculum is ready.

    Opening this worksheet IS the act of reviewing, so it goes on the record —
    the Board's accountability rests on the trail rather than on any restriction.
    Deduplicated to one entry per member per curriculum per day: the page polls
    while syllabi generate, and an entry per poll would bury the trail in an
    append-only table that can never be tidied up.
    """
    try:
        await gov.require_governance(current_user, db)
        readiness = await gov.get_readiness(program_id, db)
    except gov.GovernanceServiceError as e:
        raise _err(e)

    if await gov.record_review_opened(program_id, current_user, db):
        await AuditService.log(
            AuditEventType.CURRICULUM_REVIEW_OPENED,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            target_entity="Program",
            target_id=str(program_id),
            metadata={"program_id": str(program_id)},
        )

    return readiness


# ---------------------------------------------------------------------------
# Publish readiness — the DEAN's gate
# ---------------------------------------------------------------------------

@router.get("/programs/{program_id}/publish-readiness", response_model=PublishReadiness)
async def publish_readiness(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(TenantRole.DEAN, TenantRole.ADMIN)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> PublishReadiness:
    """Whether the Dean may publish this curriculum yet, and what is left if not.

    The SAME computation as the Board's worksheet, projected to what is his: his
    execution documents, and the gate. One source of truth, two audiences.

    A separate route rather than the Board's, deliberately. Opening the Board's worksheet
    is itself an act of review and is recorded as one — a Dean checking whether he can
    publish must not appear in the Board's accountability trail as having reviewed the
    curriculum. And he does not need to see which teaching subjects are still in draft:
    that is the Board's work, and it is not waiting on him.
    """
    try:
        readiness = await gov.get_readiness(program_id, db)
        status = await gov.get_program_status(program_id, db)
    except gov.GovernanceServiceError as e:
        raise _err(e)

    return PublishReadiness(
        program_id=program_id,
        program_status=status,
        can_publish=readiness.can_publish,
        total_documents=readiness.dean_document_count,
        approved_documents=readiness.dean_approved_count,
        documents=[i for i in readiness.items if i.owner == "DEAN"],
    )


# ---------------------------------------------------------------------------
# There is no bulk generation endpoint, and there must not be.
#
# POST /programs/{id}/syllabus/generate used to queue an AI job for every subject in the
# curriculum at once — forty syllabi, three hundred model calls, on one click. A Board of
# Studies does not decide to draft forty syllabi. It decides, subject by subject, whether
# THIS one wants an AI draft or is better written by the professor who has taught it for
# fifteen years, and the interface should ask it that question rather than assume the
# answer.
#
# Generation is now requested per syllabus, by the Board, at POST /syllabuses/{id}/generate
# — which is where it was always really decided.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Approve + lock — the only freeze, and it is permanent
# ---------------------------------------------------------------------------

@router.post("/programs/{program_id}/approve", status_code=200)
async def approve_curriculum(
    program_id: UUID,
    payload: ApproveCurriculumRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> dict:
    """Approve AND lock. Refused unless every subject has an approved official
    syllabus (422 SYLLABUS_INCOMPLETE).

    The curriculum, its syllabi and its elective baskets all become read-only for
    everyone, permanently. The Dean may then publish it — publishing does not
    unlock anything. A later academic change is a new curriculum version.
    """
    try:
        await gov.require_governance(current_user, db)
        locked = await gov.approve_and_lock(
            program_id, decided_by=current_user.user_id, comment=payload.comment, db=db,
        )
    except gov.GovernanceServiceError as e:
        raise _err(e)

    for event in (AuditEventType.CURRICULUM_APPROVED, AuditEventType.CURRICULUM_LOCKED):
        await AuditService.log(
            event,
            actor_user_id=current_user.user_id,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            schema_name=current_user.schema_name,
            target_entity="Program",
            target_id=str(program_id),
            # program_id is stamped even though target_id already holds it: the
            # governance trail reads metadata->>'program_id' uniformly across every
            # entity type, and the APPROVAL is the one entry it can least afford to
            # miss — a Board member approves without a second signature, so this row
            # is the whole of the accountability for that act.
            metadata={
                "program_id": str(program_id),
                "comment": payload.comment,
                "syllabi_locked": locked,
            },
        )

    # Tell the Dean their curriculum is finalized, and what changed. Best-effort:
    # a notification failure must not undo an approval that has already committed.
    await _notify_dean_finalized(program_id, current_user, db)

    return {"program_id": str(program_id), "status": "APPROVED", "syllabi_locked": locked}


async def _notify_dean_finalized(
    program_id: UUID, actor: CurrentUser, db: AsyncSession
) -> None:
    """'The Board has reviewed and finalized your curriculum.'

    The Dean submitted a plan and gets back something the Board may have revised
    substantially — and they cannot edit it, only publish it. So the notification
    carries the change summary: the Dean should know what they are publishing
    before they publish it.
    """
    import logging

    from sqlalchemy import text

    from app.core.notifications.models import NotificationType
    from app.core.notifications.service import NotificationService

    logger = logging.getLogger("vidya.governance")
    try:
        row = (
            await db.execute(
                text(
                    "SELECT p.title, p.submitted_by_user_id, u.email, u.full_name "
                    "FROM programs p LEFT JOIN users u ON u.id = p.submitted_by_user_id "
                    "WHERE p.id = :p"
                ),
                {"p": str(program_id)},
            )
        ).mappings().first()
        if not row or not row["submitted_by_user_id"]:
            return

        info = await gov.get_governance_info(actor.tenant_id, db)
        summary = await gov.get_change_summary(program_id, actor.tenant_id, db)

        # What the Dean must actually DO next, which depends on whether the curriculum
        # contains work of his. A curriculum with an internship is not ready to publish
        # the moment the Board finishes with it — it is ready for HIM to start.
        readiness = await gov.get_readiness(program_id, db)
        outstanding = readiness.dean_document_count - readiness.dean_approved_count

        if outstanding > 0:
            next_step = (
                f" You can now prepare the {outstanding} execution document"
                f"{'' if outstanding == 1 else 's'} this curriculum needs — its "
                "internship, project and seminar guidelines. The curriculum can be "
                "published once they are approved."
            )
        else:
            next_step = " You can publish it when ready."

        if summary.total_changes:
            changes = "; ".join(
                f"{line.label}" + (f" x{line.count}" if line.count > 1 else "")
                for line in summary.lines
            )
            body = (
                f"The {info.body_label} has reviewed and finalized the curriculum "
                f"for {row['title']}. Changes made: {changes}.{next_step}"
            )
        else:
            body = (
                f"The {info.body_label} has reviewed and finalized the curriculum "
                f"for {row['title']} with no changes.{next_step}"
            )

        await NotificationService.send(
            NotificationType.CURRICULUM_FINALIZED,
            recipient_user_id=row["submitted_by_user_id"],
            recipient_email=row["email"],
            title=f"{info.body_label} has finalized your curriculum",
            body=body,
            entity_type="Program",
            entity_id=str(program_id),
            db=db,
        )
    except Exception:
        logger.warning(
            "governance.approve: dean notification failed (non-blocking) program=%s",
            program_id, exc_info=True,
        )


# ---------------------------------------------------------------------------
# What the Board changed — shown to the Dean before publishing
# ---------------------------------------------------------------------------

@router.get("/programs/{program_id}/changes", response_model=ChangeSummary)
async def curriculum_changes(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_HISTORY_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> ChangeSummary:
    """Everything the Board did to this curriculum while it held it, grouped and
    counted — the summary the Dean reads before publishing.

    Derived from the audit log, scoped to events raised after the Dean submitted.
    """
    try:
        return await gov.get_change_summary(program_id, current_user.tenant_id, db)
    except gov.GovernanceServiceError as e:
        raise _err(e)


@router.get("/programs/{program_id}/trail", response_model=list[TrailEntry])
async def governance_trail(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_HISTORY_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[TrailEntry]:
    """The full governance trail: who reviewed, who modified, who approved, when.

    The Board has no separation of duties — a single member may enhance a
    curriculum, write its official syllabus, approve it and lock it, alone. That
    is deliberate: the Board is one academic authority, not a ladder of approval
    levels. Accountability comes from this record instead of from a restriction,
    which is why it is a first-class read rather than something buried in the raw
    audit table.

    Assembled from the append-only audit log, so no entry can be altered or
    removed after the fact.
    """
    try:
        return await gov.get_audit_trail(program_id, current_user.tenant_id, db)
    except gov.GovernanceServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/programs/{program_id}/history", response_model=list[ApprovalRequestOut])
async def approval_history(
    program_id: UUID,
    current_user: CurrentUser = Depends(require_roles(*_HISTORY_READ)),
    db: AsyncSession = Depends(get_tenant_db_dep),
) -> list[ApprovalRequestOut]:
    """Every submit -> approve this curriculum has been through."""
    rows = await gov.get_history(program_id, db)
    return [ApprovalRequestOut(**r) for r in rows]
