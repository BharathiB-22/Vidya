"""Faculty responsibility grants — service layer (ERP Onboarding Phase 1.5).

Mirrors ``FacultyProgramService`` exactly: validate-FACULTY → grant / revoke /
reactivate-in-place / list, soft-revoke only, audited.  A single FACULTY account
holds any number of active grants (GUIDE / EVALUATOR / BOARD / DEAN); the base
``users.role`` stays FACULTY and login is never affected.

Service does NOT call ``db.commit()`` — it runs under the ``_admin_db``
dependency's ``session.begin()`` (or a caller-managed transaction), which
commits the whole run atomically.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_log.models import AuditEventType
from app.core.audit_log.service import AuditService
from app.core.onboarding.faculty_role_grant_schemas import (
    GRANTABLE_ROLES,
    FacultyInfo,
    FacultyRoleGrantListResponse,
    FacultyRoleGrantOut,
    normalize_role_code,
)
from app.modules.m_academics.models import FacultyRoleGrant

# Governance: who may grant/revoke which responsibilities.  Grantable
# responsibilities are GUIDE / EVALUATOR / BOARD (DEAN is a primary role, not a
# grant — see GRANTABLE_ROLES).
#   ADMIN (and SUPER_ADMIN) → any grantable responsibility, including BOARD.
#   DEAN  → academic responsibilities inside their department only (GUIDE/EVALUATOR).
# BOARD members run examination governance / highly sensitive workflows, so BOARD
# stays ADMIN-only.  This mirrors the PRD: "AI advises, humans decide" —
# consequential authority changes need the right human.
DEAN_GRANTABLE: frozenset[str] = frozenset({"GUIDE", "EVALUATOR"})


class FacultyRoleGrantServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _authorize_actor(actor_role: str | None, role_code: str) -> None:
    """Enforce who may grant/revoke a given responsibility.

    ADMIN / SUPER_ADMIN may manage any grantable role.  DEAN may manage only
    GUIDE / EVALUATOR.  Anything else is forbidden.  ``role_code`` must already
    be normalised + validated against ``GRANTABLE_ROLES``.
    """
    role = (actor_role or "").strip().upper()
    if role in {"ADMIN", "SUPER_ADMIN"}:
        return
    if role == "DEAN":
        if role_code in DEAN_GRANTABLE:
            return
        raise FacultyRoleGrantServiceError(
            "FORBIDDEN",
            f"A Dean may only assign or remove {', '.join(sorted(DEAN_GRANTABLE))}. "
            f"'{role_code}' requires an Administrator.",
            403,
        )
    raise FacultyRoleGrantServiceError(
        "FORBIDDEN",
        "You do not have permission to manage faculty responsibilities.",
        403,
    )


async def _validate_faculty(faculty_user_id: UUID, db: AsyncSession) -> FacultyInfo:
    row = (
        await db.execute(
            text("SELECT id, full_name, email, role, is_active FROM users WHERE id = :id"),
            {"id": str(faculty_user_id)},
        )
    ).mappings().one_or_none()
    if row is None:
        raise FacultyRoleGrantServiceError("USER_NOT_FOUND", "Faculty user not found.", 404)
    if not row["is_active"]:
        raise FacultyRoleGrantServiceError("USER_INACTIVE", "Faculty user is inactive.")
    if row["role"] != "FACULTY":
        raise FacultyRoleGrantServiceError(
            "INVALID_ROLE",
            f"User role is '{row['role']}'; only FACULTY users may hold responsibility grants. "
            "Responsibilities are grants on a single FACULTY account, never separate roles.",
        )
    return FacultyInfo(id=row["id"], full_name=row["full_name"], email=row["email"])


def _validate_role_code(role_code: str) -> str:
    rc = normalize_role_code(role_code)
    if rc not in GRANTABLE_ROLES:
        raise FacultyRoleGrantServiceError(
            "INVALID_ROLE_CODE",
            f"'{rc}' is not a grantable responsibility. "
            f"Allowed: {', '.join(sorted(GRANTABLE_ROLES))}.",
        )
    return rc


def _to_out(row: FacultyRoleGrant, faculty: FacultyInfo | None, *, reactivated: bool = False) -> FacultyRoleGrantOut:
    return FacultyRoleGrantOut(
        id=row.id,
        faculty_user_id=row.faculty_user_id,
        role_code=row.role_code,
        is_active=row.is_active,
        granted_by=row.granted_by,
        granted_at=row.granted_at,
        revoked_by=row.revoked_by,
        revoked_at=row.revoked_at,
        faculty=faculty,
        reactivated=reactivated,
    )


class FacultyRoleGrantService:

    @staticmethod
    async def grant(
        db: AsyncSession,
        *,
        faculty_user_id: UUID,
        role_code: str,
        granted_by: UUID,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> FacultyRoleGrantOut:
        """Grant a responsibility to a FACULTY account.

        * Active grant already exists → ``DUPLICATE_GRANT``.
        * A revoked row exists → reactivated in place (``reactivated=True``).
        * Otherwise a new row is inserted.
        """
        rc = _validate_role_code(role_code)
        _authorize_actor(actor_role, rc)
        faculty = await _validate_faculty(faculty_user_id, db)

        existing = (
            await db.execute(
                select(FacultyRoleGrant).where(
                    and_(
                        FacultyRoleGrant.faculty_user_id == faculty_user_id,
                        FacultyRoleGrant.role_code == rc,
                    )
                )
            )
        ).scalars().all()

        active = next((r for r in existing if r.is_active), None)
        if active is not None:
            raise FacultyRoleGrantServiceError(
                "DUPLICATE_GRANT",
                f"This faculty member already holds an active {rc} responsibility.",
            )

        reactivated = False
        if existing:
            row = max(existing, key=lambda r: r.revoked_at or r.granted_at)
            row.is_active = True
            row.granted_by = granted_by
            row.granted_at = datetime.now(timezone.utc)
            row.revoked_by = None
            row.revoked_at = None
            row.updated_at = datetime.now(timezone.utc)
            reactivated = True
        else:
            row = FacultyRoleGrant(
                faculty_user_id=faculty_user_id,
                role_code=rc,
                is_active=True,
                granted_by=granted_by,
            )
            db.add(row)

        await db.flush()
        await db.refresh(row)

        await AuditService.log(
            AuditEventType.FACULTY_ROLE_GRANTED,
            actor_user_id=granted_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="FacultyRoleGrant",
            target_id=str(row.id),
            metadata={
                "faculty_user_id": str(faculty_user_id),
                "role_code": rc,
                "reactivated": reactivated,
            },
        )
        return _to_out(row, faculty, reactivated=reactivated)

    @staticmethod
    async def revoke(
        db: AsyncSession,
        *,
        faculty_user_id: UUID,
        role_code: str,
        revoked_by: UUID,
        actor_role: str | None = None,
        tenant_id: UUID | None = None,
        schema_name: str | None = None,
    ) -> FacultyRoleGrantOut:
        """Soft-revoke the active grant for (faculty, role_code)."""
        rc = _validate_role_code(role_code)
        _authorize_actor(actor_role, rc)
        faculty = await _validate_faculty(faculty_user_id, db)

        row = (
            await db.execute(
                select(FacultyRoleGrant).where(
                    and_(
                        FacultyRoleGrant.faculty_user_id == faculty_user_id,
                        FacultyRoleGrant.role_code == rc,
                        FacultyRoleGrant.is_active.is_(True),
                    )
                )
            )
        ).scalars().one_or_none()
        if row is None:
            raise FacultyRoleGrantServiceError(
                "NOT_FOUND",
                f"No active {rc} responsibility found for this faculty member.",
                404,
            )

        row.is_active = False
        row.revoked_by = revoked_by
        row.revoked_at = datetime.now(timezone.utc)
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(row)

        await AuditService.log(
            AuditEventType.FACULTY_ROLE_REVOKED,
            actor_user_id=revoked_by,
            actor_role=actor_role,
            tenant_id=tenant_id,
            schema_name=schema_name,
            target_entity="FacultyRoleGrant",
            target_id=str(row.id),
            metadata={"faculty_user_id": str(faculty_user_id), "role_code": rc},
        )
        return _to_out(row, faculty)

    @staticmethod
    async def list_grants(
        db: AsyncSession,
        *,
        faculty_user_id: UUID,
        include_inactive: bool = False,
    ) -> FacultyRoleGrantListResponse:
        stmt = select(FacultyRoleGrant).where(
            FacultyRoleGrant.faculty_user_id == faculty_user_id
        )
        if not include_inactive:
            stmt = stmt.where(FacultyRoleGrant.is_active.is_(True))
        rows = (await db.execute(stmt.order_by(FacultyRoleGrant.role_code))).scalars().all()

        faculty = None
        if rows:
            try:
                faculty = await _validate_faculty(faculty_user_id, db)
            except FacultyRoleGrantServiceError:
                faculty = None
        items = [_to_out(r, faculty) for r in rows]
        return FacultyRoleGrantListResponse(total=len(items), items=items)

    @staticmethod
    async def list_faculty_for_role(
        db: AsyncSession,
        *,
        role_code: str,
        include_inactive: bool = False,
    ) -> FacultyRoleGrantListResponse:
        rc = _validate_role_code(role_code)
        stmt = select(FacultyRoleGrant).where(FacultyRoleGrant.role_code == rc)
        if not include_inactive:
            stmt = stmt.where(FacultyRoleGrant.is_active.is_(True))
        rows = (await db.execute(stmt)).scalars().all()

        # Enrich faculty identity in one query.
        out: list[FacultyRoleGrantOut] = []
        if rows:
            ids = list({str(r.faculty_user_id) for r in rows})
            frows = (
                await db.execute(
                    text("SELECT id::text, full_name, email FROM users WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
            ).mappings().all()
            fmap = {r["id"]: r for r in frows}
            for r in rows:
                f = fmap.get(str(r.faculty_user_id))
                info = FacultyInfo(id=f["id"], full_name=f["full_name"], email=f["email"]) if f else None
                out.append(_to_out(r, info))
        return FacultyRoleGrantListResponse(total=len(out), items=out)
