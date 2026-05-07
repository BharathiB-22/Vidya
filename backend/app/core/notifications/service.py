import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.models import NotificationType
from app.core.notifications.repository import NotificationRepository
from app.core.notifications.schemas import (
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    MarkReadResponse,
)

logger = logging.getLogger("vidya.notifications")


class NotificationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotificationService:

    @staticmethod
    async def send(
        notification_type: NotificationType,
        *,
        recipient_user_id: UUID,
        recipient_email: str | None,
        title: str,
        body: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        db: AsyncSession,
    ) -> NotificationResponse:
        """Create an in-app notification and optionally dispatch an email.

        db must be a tenant-scoped session (search_path set to the tenant
        schema).  Email dispatch is fire-and-forget — a dispatch failure is
        logged but never propagated to the caller.
        """
        from app.config import settings

        notif = await NotificationRepository.create(
            NotificationCreate(
                recipient_user_id=recipient_user_id,
                notification_type=notification_type,
                title=title,
                body=body,
                entity_type=entity_type,
                entity_id=entity_id,
            ),
            db=db,
        )
        await db.commit()

        if settings.EMAIL_NOTIFICATIONS_ENABLED and recipient_email:
            _dispatch_email(recipient_email=recipient_email, subject=title, body_text=body)

        return NotificationResponse.model_validate(notif)

    @staticmethod
    async def query(
        *,
        current_user_id: UUID,
        is_read: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        db: AsyncSession,
    ) -> NotificationListResponse:
        offset = (page - 1) * page_size

        total = await NotificationRepository.count(
            recipient_user_id=current_user_id, is_read=is_read, db=db
        )
        unread_count = await NotificationRepository.count_unread(
            recipient_user_id=current_user_id, db=db
        )
        rows = await NotificationRepository.list(
            recipient_user_id=current_user_id,
            is_read=is_read,
            offset=offset,
            limit=page_size,
            db=db,
        )
        items = [NotificationResponse.model_validate(r) for r in rows]
        return NotificationListResponse(
            total=total,
            unread_count=unread_count,
            page=page,
            page_size=page_size,
            items=items,
        )

    @staticmethod
    async def mark_read(
        notification_id: UUID,
        *,
        current_user_id: UUID,
        db: AsyncSession,
    ) -> MarkReadResponse:
        notif = await NotificationRepository.mark_read(
            notification_id, recipient_user_id=current_user_id, db=db
        )
        if notif is None:
            # Distinguish not-found vs already-read by fetching the row.
            existing = await NotificationRepository.get_by_id(
                notification_id, recipient_user_id=current_user_id, db=db
            )
            if existing is None:
                raise NotificationError("NOT_FOUND", "Notification not found", 404)
            raise NotificationError("ALREADY_READ", "Notification is already read", 409)
        await db.commit()
        return MarkReadResponse.model_validate(notif)

    @staticmethod
    async def mark_all_read(
        *,
        current_user_id: UUID,
        db: AsyncSession,
    ) -> dict:
        n = await NotificationRepository.mark_all_read(
            recipient_user_id=current_user_id, db=db
        )
        await db.commit()
        return {"marked": n}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dispatch_email(*, recipient_email: str, subject: str, body_text: str) -> None:
    """Fire-and-forget Celery email dispatch. Swallows errors."""
    try:
        from app.workers.tasks.send_email import send_email
        send_email.apply_async(
            kwargs={
                "recipient_email": recipient_email,
                "subject": subject,
                "body_text": body_text,
            }
        )
    except Exception:
        logger.exception(
            "email_dispatch_failed recipient=%s subject=%r",
            recipient_email,
            subject,
        )
