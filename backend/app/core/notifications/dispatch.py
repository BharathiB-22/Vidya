"""Notification dispatch helpers — Phase 1 Wave 1 foundation.

Thin recipient-resolution layer over ``NotificationService.send``.  Every domain
event should call one of these helpers instead of hand-resolving recipients, so
recipient logic (who is the dean of this program? who is enrolled in this
section?) lives in exactly one place.

Transaction note
----------------
``NotificationService.send`` commits its own row.  Call these helpers **after**
the domain mutation has been committed (mirrors the existing syllabus / course
-assignment emitters), never mid-transaction.

Failures never propagate: a dispatch problem must not fail the domain action, so
each send is best-effort and logged.
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.models import NotificationType
from app.core.notifications.service import NotificationService

logger = logging.getLogger("vidya.notifications.dispatch")


async def _email_for(user_id: UUID, db: AsyncSession) -> str | None:
    row = (
        await db.execute(
            text("SELECT email FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
    ).one_or_none()
    return row[0] if row else None


async def notify_user(
    db: AsyncSession,
    *,
    notification_type: NotificationType,
    recipient_user_id: UUID,
    title: str,
    body: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> None:
    """Send one notification to one user (best-effort)."""
    try:
        email = await _email_for(recipient_user_id, db)
        await NotificationService.send(
            notification_type,
            recipient_user_id=recipient_user_id,
            recipient_email=email,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
            db=db,
        )
    except Exception:
        logger.exception(
            "notify_user failed type=%s recipient=%s", notification_type, recipient_user_id
        )


async def notify_program_deans(
    db: AsyncSession,
    *,
    notification_type: NotificationType,
    program_id: UUID,
    title: str,
    body: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> int:
    """Notify every DEAN who governs ``program_id`` (dean_program_assignments).

    Returns the number of deans notified.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT DISTINCT dean_user_id FROM dean_program_assignments "
                    "WHERE program_id = :pid AND is_active = true"
                ),
                {"pid": str(program_id)},
            )
        ).fetchall()
    except Exception:
        logger.exception("notify_program_deans: dean lookup failed program=%s", program_id)
        return 0

    count = 0
    for (dean_user_id,) in rows:
        await notify_user(
            db,
            notification_type=notification_type,
            recipient_user_id=dean_user_id,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        count += 1
    return count


async def notify_section_students(
    db: AsyncSession,
    *,
    notification_type: NotificationType,
    section_id: UUID,
    title: str,
    body: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> int:
    """Notify every student actively enrolled in ``section_id``.

    Provided for the Wave 2 "material uploaded / assignment published" flows.
    Returns the number of students notified.
    """
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT student_id FROM acad_enrollments "
                    "WHERE section_id = :sid AND is_active = true"
                ),
                {"sid": str(section_id)},
            )
        ).fetchall()
    except Exception:
        logger.exception("notify_section_students: lookup failed section=%s", section_id)
        return 0

    count = 0
    for (student_id,) in rows:
        await notify_user(
            db,
            notification_type=notification_type,
            recipient_user_id=student_id,
            title=title,
            body=body,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        count += 1
    return count
