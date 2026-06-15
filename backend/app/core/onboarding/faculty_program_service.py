"""Faculty ↔ Program assignment service — ERP Onboarding Phase 1 / Step 3.

Manages the many-to-many teaching scope between FACULTY users and academic
programs (``acad_programs``).  Distinct from the per-course ``SubjectAssignment``
(course + semester) and from a faculty's home department.

Invariants
----------
* **Soft revoke only.**  Rows are never hard-deleted; revocation stamps
  ``is_active=False`` + ``revoked_by`` + ``revoked_at``.
* **At most one ACTIVE assignment** per ``(faculty_user_id, program_id)``.
  Enforced in-app by a pre-check and at the DB by the partial-unique index
  ``uq_fpa_active_faculty_program`` (``WHERE is_active``).
* **Reactivation reuses history.**  Assigning a faculty to a program they were
  previously revoked from flips the existing revoked row back to active rather
  than inserting a duplicate — keeping one row per relationship.
* **Tenant-safe.**  Every statement runs inside the caller's tenant search_path;
  no cross-schema access, no tenant_id leakage.
* **Audit-friendly.**  Each mutation emits an AuditLog entry (non-blocking).

Transaction boundary: the service does NOT commit.  It runs inside the
onboarding ``_admin_db`` dependency's ``session.begin()`` block, which commits
the whole call atomically (or rolls it back on any error).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.onboarding.faculty_program_schemas import (
    FacultyInfo,
    FacultyProgramListResponse,
    FacultyProgramOut,
    ProgramInfo,
)
from app.modules.m_academics.models import FacultyProgramAssignment

logger = logging.getLogger("vidya.onboarding.faculty_program")


class FacultyProgramServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

async def _validate_faculty(faculty_user_id: UUID, db: AsyncSession) -> FacultyInfo:
    row = (
        await db.execute(
            text("SELECT id, full_name, email, role, is_active FROM users WHERE id = :id"),
            {"id": str(faculty_user_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise FacultyProgramServiceError("USER_NOT_FOUND", "Faculty user not found.", 404)
    if not row["is_active"]:
        raise FacultyProgramServiceError("USER_INACTIVE", "Faculty user is inactive.")
    if row["role"] != "FACULTY":
        raise FacultyProgramServiceError(
            "INVALID_ROLE",
            f"User role is '{row['role']}'; only FACULTY users may be assigned to programs.",
        )
    return FacultyInfo(id=row["id"], full_name=row["full_name"], email=row["email"])


async def _validate_program(program_id: UUID, db: AsyncSession) -> ProgramInfo:
    row = (
        await db.execute(
            text("SELECT id, code, name FROM acad_programs WHERE id = :id"),
            {"id": str(program_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise FacultyProgramServiceError("PROGRAM_NOT_FOUND", "Program not found.", 404)
    return ProgramInfo(id=row["id"], code=row["code"], name=row["name"])


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

async def _enrich(
    rows: list[FacultyProgramAssignment], db: AsyncSession
) -> list[FacultyProgramOut]:
    if not rows:
        return []

    faculty_ids = list({str(r.faculty_user_id) for r in rows})
    program_ids = list({str(r.program_id) for r in rows})

    faculty_rows = (
        await db.execute(
            text("SELECT id::text, full_name, email FROM users WHERE id = ANY(:ids)"),
            {"ids": faculty_ids},
        )
    ).mappings().all()
    program_rows = (
        await db.execute(
            text("SELECT id::text, code, name FROM acad_programs WHERE id = ANY(:ids)"),
            {"ids": program_ids},
        )
    ).mappings().all()

    fac_map = {r["id"]: r for r in faculty_rows}
    prog_map = {r["id"]: r for r in program_rows}

    out: list[FacultyProgramOut] = []
    for r in rows:
        f = fac_map.get(str(r.faculty_user_id))
        p = prog_map.get(str(r.program_id))
        out.append(
            FacultyProgramOut(
                id=r.id,
                faculty_user_id=r.faculty_user_id,
                program_id=r.program_id,
                is_active=r.is_active,
                assigned_by=r.assigned_by,
                assigned_at=r.assigned_at,
                revoked_by=r.revoked_by,
                revoked_at=r.revoked_at,
                faculty=FacultyInfo(id=f["id"], full_name=f["full_name"], email=f["email"]) if f else None,
                program=ProgramInfo(id=p["id"], code=p["code"], name=p["name"]) if p else None,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class FacultyProgramService:

    @staticmethod
    async def assign_program(
        db: AsyncSession,
        *,
        faculty_user_id: UUID,
        program_id: UUID,
        assigned_by: UUID,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> FacultyProgramOut:
        """Grant a faculty teaching scope on a program.

        * Active assignment already exists → ``DUPLICATE_ASSIGNMENT``.
        * A revoked row exists → reactivated in place (``reactivated=True``).
        * Otherwise a new row is inserted.
        """
        faculty = await _validate_faculty(faculty_user_id, db)
        program = await _validate_program(program_id, db)

        existing = (
            await db.execute(
                select(FacultyProgramAssignment).where(
                    and_(
                        FacultyProgramAssignment.faculty_user_id == faculty_user_id,
                        FacultyProgramAssignment.program_id == program_id,
                    )
                )
            )
        ).scalars().all()

        active = next((r for r in existing if r.is_active), None)
        if active is not None:
            raise FacultyProgramServiceError(
                "DUPLICATE_ASSIGNMENT",
                "This faculty member already has an active assignment for this program.",
            )

        reactivated = False
        if existing:
            # Reuse the most recently touched revoked row.
            row = max(existing, key=lambda r: r.revoked_at or r.assigned_at)
            row.is_active = True
            row.assigned_by = assigned_by
            row.assigned_at = datetime.now(timezone.utc)
            row.revoked_by = None
            row.revoked_at = None
            reactivated = True
        else:
            row = FacultyProgramAssignment(
                faculty_user_id=faculty_user_id,
                program_id=program_id,
                is_active=True,
                assigned_by=assigned_by,
            )
            db.add(row)

        await db.flush()
        await db.refresh(row)

        await AuditService.log(
            AuditEventType.FACULTY_PROGRAM_ASSIGNED,
            actor_user_id=assigned_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="FacultyProgramAssignment",
            target_id=str(row.id),
            metadata={
                "faculty_user_id": str(faculty_user_id),
                "program_id": str(program_id),
                "program_code": program.code,
                "reactivated": reactivated,
            },
        )

        result = FacultyProgramOut(
            id=row.id,
            faculty_user_id=row.faculty_user_id,
            program_id=row.program_id,
            is_active=row.is_active,
            assigned_by=row.assigned_by,
            assigned_at=row.assigned_at,
            revoked_by=row.revoked_by,
            revoked_at=row.revoked_at,
            faculty=faculty,
            program=program,
            reactivated=reactivated,
        )
        return result

    @staticmethod
    async def revoke_program(
        db: AsyncSession,
        *,
        faculty_user_id: UUID,
        program_id: UUID,
        revoked_by: UUID,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> FacultyProgramOut:
        """Soft-revoke the ACTIVE assignment for (faculty, program)."""
        row = (
            await db.execute(
                select(FacultyProgramAssignment).where(
                    and_(
                        FacultyProgramAssignment.faculty_user_id == faculty_user_id,
                        FacultyProgramAssignment.program_id == program_id,
                        FacultyProgramAssignment.is_active.is_(True),
                    )
                )
            )
        ).scalars().one_or_none()
        if row is None:
            raise FacultyProgramServiceError(
                "NOT_FOUND",
                "No active assignment found for this faculty and program.",
                404,
            )

        row.is_active = False
        row.revoked_by = revoked_by
        row.revoked_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(row)

        await AuditService.log(
            AuditEventType.FACULTY_PROGRAM_REVOKED,
            actor_user_id=revoked_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="FacultyProgramAssignment",
            target_id=str(row.id),
            metadata={
                "faculty_user_id": str(faculty_user_id),
                "program_id": str(program_id),
            },
        )

        enriched = await _enrich([row], db)
        return enriched[0]

    @staticmethod
    async def list_programs(
        db: AsyncSession,
        *,
        faculty_user_id: UUID,
        include_inactive: bool = False,
    ) -> FacultyProgramListResponse:
        """List program assignments held by one faculty member."""
        stmt = select(FacultyProgramAssignment).where(
            FacultyProgramAssignment.faculty_user_id == faculty_user_id
        )
        if not include_inactive:
            stmt = stmt.where(FacultyProgramAssignment.is_active.is_(True))
        stmt = stmt.order_by(FacultyProgramAssignment.assigned_at.desc())
        rows = (await db.execute(stmt)).scalars().all()
        items = await _enrich(list(rows), db)
        return FacultyProgramListResponse(total=len(items), items=items)

    @staticmethod
    async def list_faculty_for_program(
        db: AsyncSession,
        *,
        program_id: UUID,
        include_inactive: bool = False,
    ) -> FacultyProgramListResponse:
        """List faculty assigned to one program."""
        stmt = select(FacultyProgramAssignment).where(
            FacultyProgramAssignment.program_id == program_id
        )
        if not include_inactive:
            stmt = stmt.where(FacultyProgramAssignment.is_active.is_(True))
        stmt = stmt.order_by(FacultyProgramAssignment.assigned_at.desc())
        rows = (await db.execute(stmt)).scalars().all()
        items = await _enrich(list(rows), db)
        return FacultyProgramListResponse(total=len(items), items=items)
