from uuid import UUID

from sqlalchemy import and_, false, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.notifications.models import Notification
from app.core.notifications.schemas import NotificationCreate


class NotificationRepository:

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filters(
        *,
        recipient_user_id: UUID,
        is_read: bool | None,
    ) -> list:
        clauses = [Notification.recipient_user_id == recipient_user_id]
        if is_read is not None:
            clauses.append(Notification.is_read == is_read)
        return clauses

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @staticmethod
    async def create(
        create_data: NotificationCreate,
        *,
        db: AsyncSession,
    ) -> Notification:
        notif = Notification(
            recipient_user_id=create_data.recipient_user_id,
            notification_type=create_data.notification_type.value,
            title=create_data.title,
            body=create_data.body,
            entity_type=create_data.entity_type,
            entity_id=create_data.entity_id,
        )
        db.add(notif)
        await db.flush()
        await db.refresh(notif)
        return notif

    @staticmethod
    async def mark_read(
        notification_id: UUID,
        *,
        recipient_user_id: UUID,
        db: AsyncSession,
    ) -> Notification | None:
        """Set is_read=True and read_at=now() for one notification.

        Scoped to recipient_user_id — prevents cross-user mutations.
        Returns None if the row does not exist, belongs to another user,
        or is already read.
        """
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.id == notification_id,
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.is_read == false(),
                )
            )
            .values(is_read=True, read_at=func.now())
            .returning(Notification)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def mark_all_read(
        *,
        recipient_user_id: UUID,
        db: AsyncSession,
    ) -> int:
        """Mark every unread notification for the user as read.

        Returns the count of rows updated.
        """
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.recipient_user_id == recipient_user_id,
                    Notification.is_read == false(),
                )
            )
            .values(is_read=True, read_at=func.now())
        )
        result = await db.execute(stmt)
        return result.rowcount

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_by_id(
        notification_id: UUID,
        *,
        recipient_user_id: UUID,
        db: AsyncSession,
    ) -> Notification | None:
        result = await db.execute(
            select(Notification).where(
                and_(
                    Notification.id == notification_id,
                    Notification.recipient_user_id == recipient_user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        *,
        recipient_user_id: UUID,
        is_read: bool | None = None,
        offset: int = 0,
        limit: int = 50,
        db: AsyncSession,
    ) -> list[Notification]:
        clauses = NotificationRepository._build_filters(
            recipient_user_id=recipient_user_id,
            is_read=is_read,
        )
        stmt = (
            select(Notification)
            .where(and_(*clauses))
            .order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def count(
        *,
        recipient_user_id: UUID,
        is_read: bool | None = None,
        db: AsyncSession,
    ) -> int:
        clauses = NotificationRepository._build_filters(
            recipient_user_id=recipient_user_id,
            is_read=is_read,
        )
        stmt = select(func.count(Notification.id)).where(and_(*clauses))
        result = await db.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def count_unread(
        *,
        recipient_user_id: UUID,
        db: AsyncSession,
    ) -> int:
        stmt = select(func.count(Notification.id)).where(
            and_(
                Notification.recipient_user_id == recipient_user_id,
                Notification.is_read == false(),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one()
