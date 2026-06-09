"""Student Lifecycle Service — H64.3.

Valid statuses and their allowed transitions:

  APPLICANT  → ENROLLED, WITHDRAWN
  ENROLLED   → ACTIVE, WITHDRAWN
  ACTIVE     → DETAINED, GRADUATED, WITHDRAWN, ALUMNI
  DETAINED   → ACTIVE, WITHDRAWN, ARCHIVED
  GRADUATED  → ALUMNI, ARCHIVED
  ALUMNI     → ARCHIVED
  WITHDRAWN  → ARCHIVED
  ARCHIVED   → (terminal — no outbound transitions)

Human-gate invariant: only ADMIN or DEAN may call transition().
The caller is responsible for the final DB commit.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.m11_sis.models import SisStudentLifecycleHistory, SisStudentProfile

# ---------------------------------------------------------------------------
# Status catalogue
# ---------------------------------------------------------------------------

ALL_STATUSES = {
    "APPLICANT", "ENROLLED", "ACTIVE",
    "DETAINED", "GRADUATED", "ALUMNI",
    "WITHDRAWN", "ARCHIVED",
}

TRANSITIONS: dict[str, list[str]] = {
    "APPLICANT": ["ENROLLED", "WITHDRAWN"],
    "ENROLLED":  ["ACTIVE", "WITHDRAWN"],
    "ACTIVE":    ["DETAINED", "GRADUATED", "WITHDRAWN", "ALUMNI"],
    "DETAINED":  ["ACTIVE", "WITHDRAWN", "ARCHIVED"],
    "GRADUATED": ["ALUMNI", "ARCHIVED"],
    "ALUMNI":    ["ARCHIVED"],
    "WITHDRAWN": ["ARCHIVED"],
    "ARCHIVED":  [],
}

STATUS_LABELS: dict[str, str] = {
    "APPLICANT": "Applicant",
    "ENROLLED":  "Enrolled",
    "ACTIVE":    "Active",
    "DETAINED":  "Detained",
    "GRADUATED": "Graduated",
    "ALUMNI":    "Alumni",
    "WITHDRAWN": "Withdrawn",
    "ARCHIVED":  "Archived",
}


class LifecycleServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code        = code
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


class StudentLifecycleService:

    @staticmethod
    async def get_status(
        student_id: UUID,
        db: AsyncSession,
    ) -> dict:
        """Return current status, allowed next transitions, and history."""
        profile = await db.get(SisStudentProfile, student_id)
        if profile is None:
            raise LifecycleServiceError("NOT_FOUND", "Student profile not found", 404)

        current = profile.lifecycle_status or "ACTIVE"
        history_q = await db.execute(
            select(SisStudentLifecycleHistory)
            .where(SisStudentLifecycleHistory.student_id == student_id)
            .order_by(SisStudentLifecycleHistory.changed_at.desc())
            .limit(20)
        )
        history = list(history_q.scalars().all())

        return {
            "student_id":        student_id,
            "current_status":    current,
            "allowed_next":      TRANSITIONS.get(current, []),
            "history":           history,
        }

    @staticmethod
    async def transition(
        student_id: UUID,
        new_status: str,
        *,
        actor_user_id: UUID,
        actor_role: str,
        reason: Optional[str],
        db: AsyncSession,
    ) -> SisStudentProfile:
        """
        Human-gate status change.  ADMIN and DEAN only.
        Appends a history row and updates the profile — caller commits.
        """
        if actor_role not in ("ADMIN", "DEAN"):
            raise LifecycleServiceError(
                "FORBIDDEN",
                "Only ADMIN or DEAN may change a student's lifecycle status.",
                403,
            )

        if new_status not in ALL_STATUSES:
            raise LifecycleServiceError(
                "INVALID_STATUS",
                f"'{new_status}' is not a valid lifecycle status. "
                f"Valid: {', '.join(sorted(ALL_STATUSES))}",
                400,
            )

        profile = await db.get(SisStudentProfile, student_id)
        if profile is None:
            raise LifecycleServiceError("NOT_FOUND", "Student profile not found", 404)

        current = profile.lifecycle_status or "ACTIVE"
        allowed = TRANSITIONS.get(current, [])

        if new_status == current:
            raise LifecycleServiceError(
                "NO_CHANGE",
                f"Student is already in status '{current}'.",
                409,
            )

        if new_status not in allowed:
            raise LifecycleServiceError(
                "INVALID_TRANSITION",
                f"Cannot transition from '{current}' to '{new_status}'. "
                f"Allowed next: {', '.join(allowed) or 'none (terminal)'}",
                422,
            )

        # Append history row first (append-only — never update/delete)
        entry = SisStudentLifecycleHistory(
            id          = _uuid.uuid4(),
            student_id  = student_id,
            from_status = current,
            to_status   = new_status,
            reason      = reason,
            changed_by  = actor_user_id,
            changed_at  = datetime.now(timezone.utc),
        )
        db.add(entry)

        # Update profile status
        profile.lifecycle_status = new_status
        profile.updated_at       = datetime.now(timezone.utc)

        # Mirror is_active: ARCHIVED and WITHDRAWN → is_active=False; all others → True
        profile.is_active = new_status not in ("ARCHIVED", "WITHDRAWN")

        await db.flush()
        return profile
