"""
SIS Semester Rollover — H54 Service.

Business rules:
  - ADMIN only (enforced at router level).
  - preview() is read-only; no DB writes.
  - commit() re-derives rows from DB (server-side re-validation) then calls
    EnrollmentService.move_student() per ready row.
  - Each move is its own committed transaction → partial success is safe.
  - Students already in the target section return outcome="skipped" (idempotent).
  - Students with no target section remain blocked; they are never moved.
  - Audit log and notifications fire automatically via move_student().

Scope filtering:
  all_programs  → every active enrollment across all batches
  program       → all batches under program_id
  batch         → all semesters in batch_id
  semester      → only sections belonging to source_semester_id
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import User
from app.modules.m_academics.models import (
    AcadBatch, AcadEnrollment, AcadProgram, AcadSection, AcadSemester,
)
from app.modules.m11_sis.enrollment_schemas import MoveStudentIn
from app.modules.m11_sis.enrollment_service import (
    EnrollmentService, EnrollmentServiceError,
)
from app.modules.m11_sis.rollover_schemas import (
    RolloverCommitResult, RolloverCommitRowResult,
    RolloverPreviewResponse, RolloverRowOut, RolloverScopeIn, RolloverSummary,
)

logger = logging.getLogger("vidya.sis.rollover")

# Dataclass-style namedtuple for internal enrollment rows
from typing import NamedTuple


class _EnrollmentRow(NamedTuple):
    enrollment_id:           UUID
    student_id:              UUID
    student_name:            str
    student_email:           str
    current_section_id:      UUID
    current_section_name:    str
    current_semester_id:     UUID
    current_semester_number: int
    batch_id:                UUID
    batch_name:              str
    program_name:            str


class RolloverService:

    # ------------------------------------------------------------------
    # Public: preview (read-only)
    # ------------------------------------------------------------------

    @staticmethod
    async def preview(
        scope: RolloverScopeIn,
        db: AsyncSession,
    ) -> RolloverPreviewResponse:
        rows = await RolloverService._resolve_enrollment_rows(scope, db)
        preview_rows = await RolloverService._build_preview_rows(rows, db)

        ready   = sum(1 for r in preview_rows if r.status == "ready")
        blocked = len(preview_rows) - ready

        return RolloverPreviewResponse(
            scope=scope.scope,
            summary=RolloverSummary(total=len(preview_rows), ready=ready, blocked=blocked),
            rows=preview_rows,
        )

    # ------------------------------------------------------------------
    # Public: commit (re-validates server-side, then moves)
    # ------------------------------------------------------------------

    @staticmethod
    async def commit(
        scope: RolloverScopeIn,
        db: AsyncSession,
        actor_user_id: UUID | None = None,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> RolloverCommitResult:
        # Re-derive rows from DB — never trust the client's preview state.
        rows = await RolloverService._resolve_enrollment_rows(scope, db)
        preview_rows = await RolloverService._build_preview_rows(rows, db)

        commit_rows: list[RolloverCommitRowResult] = []
        moved = skipped = errors = 0

        for pr in preview_rows:
            if pr.status == "blocked":
                commit_rows.append(RolloverCommitRowResult(
                    enrollment_id=pr.enrollment_id,
                    student_id=pr.student_id,
                    student_name=pr.student_name,
                    target_section_id=None,
                    outcome="skipped",
                    reason=pr.reason,
                ))
                skipped += 1
                continue

            # status == "ready" — call move_student()
            try:
                await EnrollmentService.move_student(
                    pr.enrollment_id,
                    MoveStudentIn(target_section_id=pr.target_section_id),  # type: ignore[arg-type]
                    db,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    tenant_id=tenant_id,
                    schema_name=schema_name,
                )
                commit_rows.append(RolloverCommitRowResult(
                    enrollment_id=pr.enrollment_id,
                    student_id=pr.student_id,
                    student_name=pr.student_name,
                    target_section_id=pr.target_section_id,
                    outcome="moved",
                    reason=None,
                ))
                moved += 1
            except EnrollmentServiceError as exc:
                if exc.code == "SAME_SECTION":
                    commit_rows.append(RolloverCommitRowResult(
                        enrollment_id=pr.enrollment_id,
                        student_id=pr.student_id,
                        student_name=pr.student_name,
                        target_section_id=pr.target_section_id,
                        outcome="skipped",
                        reason="already in target section",
                    ))
                    skipped += 1
                else:
                    logger.warning(
                        "rollover_commit_error enrollment=%s code=%s msg=%s",
                        pr.enrollment_id, exc.code, exc.message,
                    )
                    commit_rows.append(RolloverCommitRowResult(
                        enrollment_id=pr.enrollment_id,
                        student_id=pr.student_id,
                        student_name=pr.student_name,
                        target_section_id=pr.target_section_id,
                        outcome="error",
                        reason=exc.message,
                    ))
                    errors += 1

        return RolloverCommitResult(moved=moved, skipped=skipped, errors=errors, rows=commit_rows)

    # ------------------------------------------------------------------
    # Internal: resolve enrolled students matching scope
    # ------------------------------------------------------------------

    @staticmethod
    async def _resolve_enrollment_rows(
        scope: RolloverScopeIn,
        db: AsyncSession,
    ) -> list[_EnrollmentRow]:
        stmt = (
            select(
                AcadEnrollment.id.label("enrollment_id"),
                AcadEnrollment.student_id,
                AcadSection.id.label("section_id"),
                AcadSection.name.label("section_name"),
                AcadSemester.id.label("semester_id"),
                AcadSemester.number.label("semester_number"),
                AcadBatch.id.label("batch_id"),
                AcadBatch.name.label("batch_name"),
                AcadProgram.name.label("program_name"),
                User.full_name.label("student_name"),
                User.email.label("student_email"),
            )
            .join(AcadSection,  AcadSection.id  == AcadEnrollment.section_id)
            .join(AcadSemester, AcadSemester.id == AcadSection.semester_id)
            .join(AcadBatch,    AcadBatch.id    == AcadSemester.batch_id)
            .join(AcadProgram,  AcadProgram.id  == AcadBatch.program_id)
            .join(User,         User.id         == AcadEnrollment.student_id)
            .where(AcadEnrollment.is_active.is_(True))
        )

        if scope.scope == "program":
            stmt = stmt.where(AcadBatch.program_id == scope.program_id)
        elif scope.scope == "batch":
            stmt = stmt.where(AcadSemester.batch_id == scope.batch_id)
        elif scope.scope == "semester":
            stmt = stmt.where(AcadSection.semester_id == scope.source_semester_id)

        stmt = stmt.order_by(AcadProgram.name, AcadBatch.name, AcadSemester.number, User.full_name)
        result = await db.execute(stmt)

        return [
            _EnrollmentRow(
                enrollment_id=row.enrollment_id,
                student_id=row.student_id,
                student_name=row.student_name,
                student_email=row.student_email,
                current_section_id=row.section_id,
                current_section_name=row.section_name,
                current_semester_id=row.semester_id,
                current_semester_number=row.semester_number,
                batch_id=row.batch_id,
                batch_name=row.batch_name,
                program_name=row.program_name,
            )
            for row in result.all()
        ]

    # ------------------------------------------------------------------
    # Internal: find target semester (N+1) in the same batch
    # ------------------------------------------------------------------

    @staticmethod
    async def _find_target_semester(
        batch_id: UUID,
        current_number: int,
        db: AsyncSession,
    ) -> AcadSemester | None:
        result = await db.execute(
            select(AcadSemester)
            .where(AcadSemester.batch_id == batch_id)
            .where(AcadSemester.number == current_number + 1)
            .where(AcadSemester.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Internal: find target section by name in the target semester
    # ------------------------------------------------------------------

    @staticmethod
    async def _find_target_section(
        target_semester_id: UUID,
        section_name: str,
        db: AsyncSession,
    ) -> AcadSection | None:
        result = await db.execute(
            select(AcadSection)
            .where(AcadSection.semester_id == target_semester_id)
            .where(AcadSection.name == section_name)
            .where(AcadSection.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Internal: build preview rows with caching to reduce DB round-trips
    # ------------------------------------------------------------------

    @staticmethod
    async def _build_preview_rows(
        enrollment_rows: list[_EnrollmentRow],
        db: AsyncSession,
    ) -> list[RolloverRowOut]:
        # Cache keyed by (batch_id, current_semester_number) → AcadSemester | None
        target_sem_cache: dict[tuple[UUID, int], AcadSemester | None] = {}
        # Cache keyed by (target_semester_id, section_name) → AcadSection | None
        target_sec_cache: dict[tuple[UUID, str], AcadSection | None] = {}

        preview_rows: list[RolloverRowOut] = []

        for er in enrollment_rows:
            sem_key = (er.batch_id, er.current_semester_number)
            if sem_key not in target_sem_cache:
                target_sem_cache[sem_key] = await RolloverService._find_target_semester(
                    er.batch_id, er.current_semester_number, db
                )
            target_sem = target_sem_cache[sem_key]

            if target_sem is None:
                preview_rows.append(RolloverRowOut(
                    enrollment_id=er.enrollment_id,
                    student_id=er.student_id,
                    student_name=er.student_name,
                    student_email=er.student_email,
                    current_section_id=er.current_section_id,
                    current_section_name=er.current_section_name,
                    current_semester_number=er.current_semester_number,
                    batch_name=er.batch_name,
                    program_name=er.program_name,
                    target_semester_number=None,
                    target_section_id=None,
                    target_section_name=None,
                    status="blocked",
                    reason=f"No active Semester {er.current_semester_number + 1} found in this batch",
                ))
                continue

            sec_key = (target_sem.id, er.current_section_name)
            if sec_key not in target_sec_cache:
                target_sec_cache[sec_key] = await RolloverService._find_target_section(
                    target_sem.id, er.current_section_name, db
                )
            target_sec = target_sec_cache[sec_key]

            if target_sec is None:
                preview_rows.append(RolloverRowOut(
                    enrollment_id=er.enrollment_id,
                    student_id=er.student_id,
                    student_name=er.student_name,
                    student_email=er.student_email,
                    current_section_id=er.current_section_id,
                    current_section_name=er.current_section_name,
                    current_semester_number=er.current_semester_number,
                    batch_name=er.batch_name,
                    program_name=er.program_name,
                    target_semester_number=target_sem.number,
                    target_section_id=None,
                    target_section_name=None,
                    status="blocked",
                    reason=(
                        f"Section '{er.current_section_name}' not found "
                        f"in Semester {target_sem.number}"
                    ),
                ))
                continue

            preview_rows.append(RolloverRowOut(
                enrollment_id=er.enrollment_id,
                student_id=er.student_id,
                student_name=er.student_name,
                student_email=er.student_email,
                current_section_id=er.current_section_id,
                current_section_name=er.current_section_name,
                current_semester_number=er.current_semester_number,
                batch_name=er.batch_name,
                program_name=er.program_name,
                target_semester_number=target_sem.number,
                target_section_id=target_sec.id,
                target_section_name=target_sec.name,
                status="ready",
                reason=None,
            ))

        return preview_rows
