"""SIS Validation Report Service — H64.8.

Runs 7 data-quality checks and returns a structured report.
All checks use COUNT + limited item lists; no heavy scans.

Checks:
  1. students_without_profile      — STUDENT users with no SisStudentProfile
  2. faculty_without_profile       — FACULTY users with no SisFacultyProfile
  3. students_without_usn          — SisStudentProfile rows with usn IS NULL
  4. students_not_enrolled         — active STUDENT users with no active enrollment
  5. enrolled_inactive_section     — active enrollments in inactive sections
  6. sections_over_capacity        — sections where enrolled > max_strength
  7. lifecycle_is_active_mismatch  — profiles where lifecycle_status != is_active expectation
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth.models import TenantRole, User
from app.modules.m_academics.models import AcadEnrollment, AcadSection
from app.modules.m11_sis.models import SisFacultyProfile, SisStudentProfile
from app.modules.m11_sis.validation_schemas import (
    CheckResult,
    ValidationItem,
    ValidationReportOut,
)

MAX_ITEMS = 20


def _check(
    check_id: str,
    label: str,
    description: str,
    severity: str,
    items: list[ValidationItem],
) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        label=label,
        description=description,
        severity=severity,
        count=len(items),
        items=items,
    )


class ValidationService:

    @staticmethod
    async def generate_report(*, db: AsyncSession) -> ValidationReportOut:
        checks: list[CheckResult] = []

        # ── 1. Students without SIS profile ─────────────────────────────────
        rows = (
            await db.execute(
                select(User.id, User.full_name, User.email)
                .outerjoin(SisStudentProfile, SisStudentProfile.user_id == User.id)
                .where(
                    User.role == TenantRole.STUDENT,
                    SisStudentProfile.user_id.is_(None),
                )
                .order_by(User.full_name)
                .limit(MAX_ITEMS)
            )
        ).all()
        checks.append(_check(
            "students_without_profile",
            "Students without SIS profile",
            "STUDENT users that have no matching sis_student_profiles row. "
            "They cannot appear in the directory or have enrollment records.",
            "WARNING",
            [ValidationItem(id=r.id, detail=f"{r.full_name} ({r.email})") for r in rows],
        ))

        # ── 2. Faculty without SIS profile ──────────────────────────────────
        rows = (
            await db.execute(
                select(User.id, User.full_name, User.email)
                .outerjoin(SisFacultyProfile, SisFacultyProfile.user_id == User.id)
                .where(
                    User.role == TenantRole.FACULTY,
                    SisFacultyProfile.user_id.is_(None),
                )
                .order_by(User.full_name)
                .limit(MAX_ITEMS)
            )
        ).all()
        checks.append(_check(
            "faculty_without_profile",
            "Faculty without SIS profile",
            "FACULTY users that have no matching sis_faculty_profiles row.",
            "WARNING",
            [ValidationItem(id=r.id, detail=f"{r.full_name} ({r.email})") for r in rows],
        ))

        # ── 3. Students without USN ──────────────────────────────────────────
        rows = (
            await db.execute(
                select(SisStudentProfile.user_id, User.full_name, User.email)
                .join(User, User.id == SisStudentProfile.user_id)
                .where(SisStudentProfile.usn.is_(None))
                .order_by(User.full_name)
                .limit(MAX_ITEMS)
            )
        ).all()
        checks.append(_check(
            "students_without_usn",
            "Students without USN",
            "Student profiles where the USN field is blank. "
            "USN is needed for hall tickets and transcripts.",
            "WARNING",
            [ValidationItem(id=r.user_id, detail=f"{r.full_name} ({r.email})") for r in rows],
        ))

        # ── 4. Active students not enrolled ─────────────────────────────────
        rows = (
            await db.execute(
                select(User.id, User.full_name, User.email)
                .outerjoin(
                    AcadEnrollment,
                    (AcadEnrollment.student_id == User.id) & AcadEnrollment.is_active.is_(True),
                )
                .where(
                    User.role == TenantRole.STUDENT,
                    User.is_active.is_(True),
                    AcadEnrollment.id.is_(None),
                )
                .order_by(User.full_name)
                .limit(MAX_ITEMS)
            )
        ).all()
        checks.append(_check(
            "students_not_enrolled",
            "Active students with no section enrollment",
            "Active STUDENT users that are not assigned to any section. "
            "They will not appear on rosters or receive attendance marks.",
            "INFO",
            [ValidationItem(id=r.id, detail=f"{r.full_name} ({r.email})") for r in rows],
        ))

        # ── 5. Active enrollments in inactive sections ───────────────────────
        rows = (
            await db.execute(
                select(
                    AcadEnrollment.id,
                    User.full_name,
                    User.email,
                    AcadSection.name.label("section_name"),
                )
                .join(User, User.id == AcadEnrollment.student_id)
                .join(AcadSection, AcadSection.id == AcadEnrollment.section_id)
                .where(
                    AcadEnrollment.is_active.is_(True),
                    AcadSection.is_active.is_(False),
                )
                .order_by(User.full_name)
                .limit(MAX_ITEMS)
            )
        ).all()
        checks.append(_check(
            "enrolled_inactive_section",
            "Enrollments in inactive sections",
            "Students with an active enrollment record pointing to a deactivated section.",
            "ERROR",
            [
                ValidationItem(
                    id=r.id,
                    detail=f"{r.full_name} ({r.email}) → section '{r.section_name}'",
                )
                for r in rows
            ],
        ))

        # ── 6. Sections over capacity ────────────────────────────────────────
        subq = (
            select(AcadEnrollment.section_id, func.count().label("enrolled"))
            .where(AcadEnrollment.is_active.is_(True))
            .group_by(AcadEnrollment.section_id)
            .subquery()
        )
        rows = (
            await db.execute(
                select(
                    AcadSection.id,
                    AcadSection.name,
                    AcadSection.max_strength,
                    subq.c.enrolled,
                )
                .join(subq, subq.c.section_id == AcadSection.id)
                .where(
                    AcadSection.max_strength.isnot(None),
                    subq.c.enrolled > AcadSection.max_strength,
                )
                .order_by(AcadSection.name)
                .limit(MAX_ITEMS)
            )
        ).all()
        checks.append(_check(
            "sections_over_capacity",
            "Sections over capacity",
            "Sections where current active enrollment exceeds max_strength. "
            "This can happen after a capacity was set below the existing count.",
            "ERROR",
            [
                ValidationItem(
                    id=r.id,
                    detail=f"'{r.name}' — {r.enrolled}/{r.max_strength} seats",
                )
                for r in rows
            ],
        ))

        # ── 7. Lifecycle / is_active mismatch ────────────────────────────────
        # Students: is_active should be False when lifecycle_status is ARCHIVED or WITHDRAWN
        archived_statuses = ("ARCHIVED", "WITHDRAWN")
        rows_s = (
            await db.execute(
                select(SisStudentProfile.user_id, User.full_name, SisStudentProfile.lifecycle_status)
                .join(User, User.id == SisStudentProfile.user_id)
                .where(
                    SisStudentProfile.lifecycle_status.in_(archived_statuses),
                    SisStudentProfile.is_active.is_(True),
                )
                .order_by(User.full_name)
                .limit(MAX_ITEMS // 2)
            )
        ).all()
        rows_f = (
            await db.execute(
                select(SisFacultyProfile.user_id, User.full_name, SisFacultyProfile.lifecycle_status)
                .join(User, User.id == SisFacultyProfile.user_id)
                .where(
                    SisFacultyProfile.lifecycle_status == "ARCHIVED",
                    SisFacultyProfile.is_active.is_(True),
                )
                .order_by(User.full_name)
                .limit(MAX_ITEMS // 2)
            )
        ).all()
        mismatch_items = [
            ValidationItem(
                id=r.user_id,
                detail=f"{r.full_name} — status={r.lifecycle_status} but is_active=True",
            )
            for r in [*rows_s, *rows_f]
        ]
        checks.append(_check(
            "lifecycle_is_active_mismatch",
            "Lifecycle / is_active mismatch",
            "Profiles where lifecycle_status indicates inactive (ARCHIVED/WITHDRAWN) "
            "but the is_active flag is still True. May indicate a partial update.",
            "ERROR",
            mismatch_items,
        ))

        total = sum(c.count for c in checks)
        return ValidationReportOut(
            generated_at=datetime.now(timezone.utc),
            total_issues=total,
            checks=checks,
        )
