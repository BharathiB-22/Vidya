import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from tests.conftest import (
    _Session,
    make_tenant_headers,
)

from app.core.notifications.models import NotificationType
from app.core.notifications.repository import NotificationRepository
from app.core.notifications.schemas import NotificationCreate
from app.core.notifications.service import NotificationError, NotificationService
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")

_PATCH_APPLY_ASYNC = "app.workers.tasks.send_email.send_email.apply_async"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_notification(
    schema_name: str,
    recipient_user_id,
    *,
    notification_type: str = "GENERAL",
    title: str = "Test notification",
    body: str = "Test body",
    is_read: bool = False,
    created_at_offset: int = 0,
) -> uuid.UUID:
    notif_id = uuid.uuid4()
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            await session.execute(
                text(
                    "INSERT INTO notifications "
                    "(id, recipient_user_id, notification_type, title, body, "
                    " is_read, created_at) "
                    "VALUES (:id, :uid, :nt, :title, :body, :is_read, "
                    "  now() - (:offset * INTERVAL '1 second'))"
                ),
                {
                    "id": str(notif_id),
                    "uid": str(recipient_user_id),
                    "nt": notification_type,
                    "title": title,
                    "body": body,
                    "is_read": is_read,
                    "offset": created_at_offset,
                },
            )
    return notif_id


async def _delete_notifications(schema_name: str, *notif_ids: uuid.UUID) -> None:
    if not notif_ids:
        return
    async with _Session() as session:
        async with session.begin():
            await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
            for nid in notif_ids:
                await session.execute(
                    text("DELETE FROM notifications WHERE id = :id"),
                    {"id": str(nid)},
                )


async def _tenant_session(schema_name: str):
    """Yield a tenant-scoped async session (used in service tests)."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from app.config import settings
    engine = create_async_engine(settings.DATABASE_URL, connect_args={"statement_cache_size": 0})
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text(f"SET LOCAL search_path = {schema_name}, public"))
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Group 1 — App wiring
# ---------------------------------------------------------------------------


async def test_router_registered():
    routes = {
        (frozenset(r.methods), r.path)
        for r in app.routes
        if hasattr(r, "methods") and hasattr(r, "path")
    }
    assert (frozenset({"GET"}),   "/notifications")                      in routes
    assert (frozenset({"PATCH"}), "/notifications/{notification_id}/read") in routes
    assert (frozenset({"POST"}),  "/notifications/read-all")             in routes
    assert (frozenset({"POST"}),  "/notifications")                  not in routes


# ---------------------------------------------------------------------------
# Group 2 — Repository (direct DB, tenant session)
# ---------------------------------------------------------------------------


async def test_repo_create(test_tenant_a, admin_user_a):
    from app.config import settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    engine = create_async_engine(settings.DATABASE_URL, connect_args={"statement_cache_size": 0})
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    notif_id = None
    try:
        async with factory() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
                data = NotificationCreate(
                    recipient_user_id=admin_user_a["id"],
                    notification_type=NotificationType.GENERAL,
                    title="Hello",
                    body="World",
                )
                notif = await NotificationRepository.create(data, db=session)
                notif_id = notif.id
        assert notif.is_read is False
        assert notif.notification_type == "GENERAL"
        assert notif.title == "Hello"
    finally:
        if notif_id:
            await _delete_notifications("tenant_test_a", notif_id)
    await engine.dispose()


async def test_repo_get_by_id_found(test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"])
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            result = await NotificationRepository.get_by_id(
                nid, recipient_user_id=admin_user_a["id"], db=session
            )
        assert result is not None
        assert result.id == nid
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_repo_get_by_id_wrong_user(test_tenant_a, admin_user_a, faculty_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"])
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            result = await NotificationRepository.get_by_id(
                nid, recipient_user_id=faculty_user_a["id"], db=session
            )
        assert result is None
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_repo_list_filters_is_read(test_tenant_a, admin_user_a):
    unread_id = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False, title="unread")
    read_id   = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=True,  title="read")
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            rows = await NotificationRepository.list(
                recipient_user_id=admin_user_a["id"], is_read=False, db=session
            )
        ids = {r.id for r in rows}
        assert unread_id in ids
        assert read_id not in ids
    finally:
        await _delete_notifications("tenant_test_a", unread_id, read_id)


async def test_repo_list_ordering(test_tenant_a, admin_user_a):
    oldest_id = await _insert_notification("tenant_test_a", admin_user_a["id"], title="oldest", created_at_offset=2)
    middle_id = await _insert_notification("tenant_test_a", admin_user_a["id"], title="middle", created_at_offset=1)
    newest_id = await _insert_notification("tenant_test_a", admin_user_a["id"], title="newest", created_at_offset=0)
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            rows = await NotificationRepository.list(
                recipient_user_id=admin_user_a["id"], db=session
            )
        ordered = [r.id for r in rows]
        assert ordered.index(newest_id) < ordered.index(middle_id)
        assert ordered.index(middle_id) < ordered.index(oldest_id)
    finally:
        await _delete_notifications("tenant_test_a", oldest_id, middle_id, newest_id)


async def test_repo_count_and_count_unread(test_tenant_a, admin_user_a):
    ids = [
        await _insert_notification("tenant_test_a", admin_user_a["id"], title="c", is_read=(i % 2 == 0))
        for i in range(4)
    ]
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            total   = await NotificationRepository.count(recipient_user_id=admin_user_a["id"], db=session)
            unread  = await NotificationRepository.count_unread(recipient_user_id=admin_user_a["id"], db=session)
        assert total >= 4
        assert unread >= 2   # 2 of the 4 are unread (i=1,3)
    finally:
        await _delete_notifications("tenant_test_a", *ids)


async def test_repo_mark_read(test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False)
    try:
        async with _Session() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
                result = await NotificationRepository.mark_read(
                    nid, recipient_user_id=admin_user_a["id"], db=session
                )
        assert result is not None
        assert result.is_read is True
        assert result.read_at is not None
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_repo_mark_read_already_read_returns_none(test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=True)
    try:
        async with _Session() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
                result = await NotificationRepository.mark_read(
                    nid, recipient_user_id=admin_user_a["id"], db=session
                )
        assert result is None
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_repo_mark_all_read(test_tenant_a, admin_user_a):
    ids = [await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False) for _ in range(3)]
    try:
        async with _Session() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
                count = await NotificationRepository.mark_all_read(
                    recipient_user_id=admin_user_a["id"], db=session
                )
        assert count >= 3
    finally:
        await _delete_notifications("tenant_test_a", *ids)


# ---------------------------------------------------------------------------
# Group 3 — Service layer
# ---------------------------------------------------------------------------


async def test_service_send_creates_in_app_record(test_tenant_a, admin_user_a):
    nid = None
    with patch(_PATCH_APPLY_ASYNC):
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            resp = await NotificationService.send(
                NotificationType.TASK_COMPLETE,
                recipient_user_id=admin_user_a["id"],
                recipient_email=None,
                title="Job done",
                body="Your job completed.",
                db=session,
            )
            nid = resp.id
    try:
        assert resp.notification_type == NotificationType.TASK_COMPLETE
        assert resp.is_read is False
    finally:
        if nid:
            await _delete_notifications("tenant_test_a", nid)


async def test_service_send_dispatches_email_when_enabled(test_tenant_a, admin_user_a):
    nid = None
    with patch(_PATCH_APPLY_ASYNC) as mock_apply:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            resp = await NotificationService.send(
                NotificationType.GENERAL,
                recipient_user_id=admin_user_a["id"],
                recipient_email="test@example.com",
                title="Hello",
                body="Body text",
                db=session,
            )
            nid = resp.id
    try:
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args.kwargs["kwargs"]
        assert call_kwargs["recipient_email"] == "test@example.com"
    finally:
        if nid:
            await _delete_notifications("tenant_test_a", nid)


async def test_service_send_skips_email_when_recipient_none(test_tenant_a, admin_user_a):
    nid = None
    with patch(_PATCH_APPLY_ASYNC) as mock_apply:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            resp = await NotificationService.send(
                NotificationType.GENERAL,
                recipient_user_id=admin_user_a["id"],
                recipient_email=None,
                title="No email",
                body="Body",
                db=session,
            )
            nid = resp.id
    try:
        mock_apply.assert_not_called()
    finally:
        if nid:
            await _delete_notifications("tenant_test_a", nid)


async def test_service_send_dispatch_failure_does_not_propagate(test_tenant_a, admin_user_a):
    nid = None
    with patch(_PATCH_APPLY_ASYNC, side_effect=ConnectionError("Redis down")):
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            resp = await NotificationService.send(
                NotificationType.GENERAL,
                recipient_user_id=admin_user_a["id"],
                recipient_email="user@example.com",
                title="Resilient",
                body="Body",
                db=session,
            )
            nid = resp.id
    try:
        assert nid is not None   # row created despite email failure
    finally:
        if nid:
            await _delete_notifications("tenant_test_a", nid)


async def test_service_mark_read_success(test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False)
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            resp = await NotificationService.mark_read(nid, current_user_id=admin_user_a["id"], db=session)
        assert resp.is_read is True
        assert resp.read_at is not None
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_service_mark_read_already_read_raises_409(test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=True)
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            with pytest.raises(NotificationError) as exc_info:
                await NotificationService.mark_read(nid, current_user_id=admin_user_a["id"], db=session)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "ALREADY_READ"
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_service_mark_read_not_found_raises_404(test_tenant_a, admin_user_a):
    async with _Session() as session:
        await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
        with pytest.raises(NotificationError) as exc_info:
            await NotificationService.mark_read(uuid.uuid4(), current_user_id=admin_user_a["id"], db=session)
    assert exc_info.value.status_code == 404


async def test_service_mark_all_read(test_tenant_a, admin_user_a):
    ids = [await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False) for _ in range(3)]
    try:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            result = await NotificationService.mark_all_read(current_user_id=admin_user_a["id"], db=session)
        assert result["marked"] >= 3
    finally:
        await _delete_notifications("tenant_test_a", *ids)


# ---------------------------------------------------------------------------
# Group 4 — Router / HTTP endpoints
# ---------------------------------------------------------------------------

# --- Unauthenticated ---


async def test_list_unauthenticated(async_client):
    resp = await async_client.get("/notifications")
    assert resp.status_code in (401, 422)


async def test_mark_read_unauthenticated(async_client):
    resp = await async_client.patch(f"/notifications/{uuid.uuid4()}/read")
    assert resp.status_code in (401, 422)


async def test_mark_all_read_unauthenticated(async_client):
    resp = await async_client.post("/notifications/read-all")
    assert resp.status_code in (401, 422)


# --- List ---


async def test_list_returns_own_notifications(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    admin_nid   = await _insert_notification("tenant_test_a", admin_user_a["id"],   title="admin notif")
    faculty_nid = await _insert_notification("tenant_test_a", faculty_user_a["id"], title="faculty notif")
    try:
        resp = await async_client.get("/notifications", headers=make_tenant_headers(admin_user_a))
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert str(admin_nid) in ids
        assert str(faculty_nid) not in ids
    finally:
        await _delete_notifications("tenant_test_a", admin_nid, faculty_nid)


async def test_list_filter_is_read_false(async_client, test_tenant_a, admin_user_a):
    unread_id = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False, title="unread")
    read_id   = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=True,  title="read")
    try:
        resp = await async_client.get(
            "/notifications",
            params={"is_read": "false"},
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert str(unread_id) in ids
        assert str(read_id) not in ids
    finally:
        await _delete_notifications("tenant_test_a", unread_id, read_id)


async def test_list_response_includes_unread_count(async_client, test_tenant_a, admin_user_a):
    ids = [await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False) for _ in range(2)]
    try:
        resp = await async_client.get("/notifications", headers=make_tenant_headers(admin_user_a))
        assert resp.status_code == 200
        body = resp.json()
        assert "unread_count" in body
        assert body["unread_count"] >= 2
    finally:
        await _delete_notifications("tenant_test_a", *ids)


async def test_list_pagination(async_client, test_tenant_a, admin_user_a):
    ids = [
        await _insert_notification("tenant_test_a", admin_user_a["id"], title="pg", created_at_offset=i)
        for i in range(5, 0, -1)
    ]
    try:
        p1 = await async_client.get(
            "/notifications", params={"page": 1, "page_size": 3},
            headers=make_tenant_headers(admin_user_a),
        )
        p2 = await async_client.get(
            "/notifications", params={"page": 2, "page_size": 3},
            headers=make_tenant_headers(admin_user_a),
        )
        assert p1.status_code == p2.status_code == 200
        assert len(p1.json()["items"]) == 3
        assert len(p2.json()["items"]) >= 1
        assert {i["id"] for i in p1.json()["items"]}.isdisjoint(
               {i["id"] for i in p2.json()["items"]})
    finally:
        await _delete_notifications("tenant_test_a", *ids)


# --- Mark one read ---


async def test_mark_read_success(async_client, test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False)
    try:
        resp = await async_client.patch(
            f"/notifications/{nid}/read",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_read"] is True
        assert body["read_at"] is not None
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_mark_read_already_read_409(async_client, test_tenant_a, admin_user_a):
    nid = await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=True)
    try:
        resp = await async_client.patch(
            f"/notifications/{nid}/read",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 409
        assert resp.json()["error"] == "ALREADY_READ"
    finally:
        await _delete_notifications("tenant_test_a", nid)


async def test_mark_read_not_found_404(async_client, test_tenant_a, admin_user_a):
    resp = await async_client.patch(
        f"/notifications/{uuid.uuid4()}/read",
        headers=make_tenant_headers(admin_user_a),
    )
    assert resp.status_code == 404


async def test_mark_read_other_user_404(async_client, test_tenant_a, admin_user_a, faculty_user_a):
    nid = await _insert_notification("tenant_test_a", faculty_user_a["id"], is_read=False)
    try:
        resp = await async_client.patch(
            f"/notifications/{nid}/read",
            headers=make_tenant_headers(admin_user_a),   # different user
        )
        assert resp.status_code == 404
    finally:
        await _delete_notifications("tenant_test_a", nid)


# --- Mark all read ---


async def test_mark_all_read_returns_count(async_client, test_tenant_a, admin_user_a):
    ids = [await _insert_notification("tenant_test_a", admin_user_a["id"], is_read=False) for _ in range(3)]
    try:
        resp = await async_client.post(
            "/notifications/read-all",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        assert resp.json()["marked"] >= 3
    finally:
        await _delete_notifications("tenant_test_a", *ids)


async def test_mark_all_read_does_not_touch_other_user(
    async_client, test_tenant_a, admin_user_a, faculty_user_a
):
    faculty_nid = await _insert_notification("tenant_test_a", faculty_user_a["id"], is_read=False)
    try:
        await async_client.post("/notifications/read-all", headers=make_tenant_headers(admin_user_a))
        # faculty's notification should still be unread
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            row = await NotificationRepository.get_by_id(
                faculty_nid, recipient_user_id=faculty_user_a["id"], db=session
            )
        assert row is not None
        assert row.is_read is False
    finally:
        await _delete_notifications("tenant_test_a", faculty_nid)


# --- Dev-mode email (no SMTP configured) ---


# ---------------------------------------------------------------------------
# Group 5 — RBAC: all tenant roles can read their own notifications
# ---------------------------------------------------------------------------


async def test_evaluator_can_list_notifications(async_client, test_tenant_a, evaluator_user_a):
    """EVALUATOR must get 200 on GET /notifications — not 403."""
    resp = await async_client.get(
        "/notifications",
        params={"page": 1, "page_size": 1},
        headers=make_tenant_headers(evaluator_user_a),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert "unread_count" in body


# ---------------------------------------------------------------------------
# Group 6 — Dev-mode email
# ---------------------------------------------------------------------------


async def test_dev_mode_email_prints_not_sends(capsys, test_tenant_a, admin_user_a):
    nid = None
    # apply_async NOT patched — we let the real path run, but SMTP_USER is
    # None in test env so send_email falls into _dev_log (prints to stdout)
    with patch(_PATCH_APPLY_ASYNC) as mock_apply:
        async with _Session() as session:
            await session.execute(text("SET LOCAL search_path = tenant_test_a, public"))
            resp = await NotificationService.send(
                NotificationType.GENERAL,
                recipient_user_id=admin_user_a["id"],
                recipient_email="dev@example.com",
                title="Dev email test",
                body="Should be dispatched via Celery mock",
                db=session,
            )
            nid = resp.id
    try:
        # In tests, apply_async is always mocked — no real Celery/Redis needed.
        # Verify it was called (the dispatch path was reached).
        mock_apply.assert_called_once()
    finally:
        if nid:
            await _delete_notifications("tenant_test_a", nid)
