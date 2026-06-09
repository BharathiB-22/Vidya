"""SIS Bulk Operations Service — H64.5.

Applies a single lifecycle action to a list of student or faculty IDs.
Each item is processed independently so partial success is possible.
Human-gate: caller must be ADMIN.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.bulk_ops_schemas import BulkOpResult
from app.modules.m11_sis.lifecycle_service import (
    FacultyLifecycleService,
    LifecycleServiceError,
    StudentLifecycleService,
)

# Map UI action names to lifecycle status values
_STUDENT_ACTION_MAP = {
    "DEACTIVATE": "WITHDRAWN",
    "ARCHIVE":    "ARCHIVED",
}

_FACULTY_ACTION_MAP = {
    "DEACTIVATE": "INACTIVE",
    "ARCHIVE":    "ARCHIVED",
}


class BulkOpsService:

    @staticmethod
    async def bulk_student_action(
        student_ids: list[UUID],
        action: str,
        *,
        reason: Optional[str],
        actor_user_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ) -> BulkOpResult:
        new_status = _STUDENT_ACTION_MAP[action]
        succeeded = 0
        errors: list[str] = []

        for sid in student_ids:
            try:
                await StudentLifecycleService.transition(
                    sid,
                    new_status,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    reason=reason,
                    db=db,
                )
                succeeded += 1
            except LifecycleServiceError as exc:
                errors.append(f"{sid}: {exc.message}")
            except Exception as exc:
                errors.append(f"{sid}: unexpected error — {exc}")

        return BulkOpResult(
            action=action,
            requested=len(student_ids),
            succeeded=succeeded,
            failed=len(errors),
            errors=errors,
        )

    @staticmethod
    async def bulk_faculty_action(
        faculty_ids: list[UUID],
        action: str,
        *,
        reason: Optional[str],
        actor_user_id: UUID,
        actor_role: str,
        db: AsyncSession,
    ) -> BulkOpResult:
        new_status = _FACULTY_ACTION_MAP[action]
        succeeded = 0
        errors: list[str] = []

        for fid in faculty_ids:
            try:
                await FacultyLifecycleService.transition(
                    fid,
                    new_status,
                    actor_user_id=actor_user_id,
                    actor_role=actor_role,
                    reason=reason,
                    db=db,
                )
                succeeded += 1
            except LifecycleServiceError as exc:
                errors.append(f"{fid}: {exc.message}")
            except Exception as exc:
                errors.append(f"{fid}: unexpected error — {exc}")

        return BulkOpResult(
            action=action,
            requested=len(faculty_ids),
            succeeded=succeeded,
            failed=len(errors),
            errors=errors,
        )
