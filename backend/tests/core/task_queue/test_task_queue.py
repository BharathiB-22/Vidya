import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

from tests.conftest import (
    _Session,
    make_platform_headers,
    make_tenant_headers,
)

from app.core.task_queue.models import TaskJobStatus
from app.core.task_queue.repository import TaskJobRepository
from app.core.task_queue.schemas import TaskJobCreate
from app.core.task_queue.service import TaskQueueError, TaskQueueService
from app.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_job(
    tenant_id,
    *,
    task_type: str = "test.task",
    queue_name: str = "celery",
    status: str = "PENDING",
    created_at_offset: int = 0,
) -> uuid.UUID:
    """Insert a committed task_jobs row. created_at_offset seconds in the past."""
    job_id = uuid.uuid4()
    async with _Session() as session:
        async with session.begin():
            await session.execute(
                text(
                    "INSERT INTO public.task_jobs "
                    "(id, tenant_id, task_type, queue_name, status, created_at) "
                    "VALUES (:id, :tid, :tt, :qn, :st, "
                    "  now() - (:offset * INTERVAL '1 second'))"
                ),
                {
                    "id": str(job_id),
                    "tid": str(tenant_id),
                    "tt": task_type,
                    "qn": queue_name,
                    "st": status,
                    "offset": created_at_offset,
                },
            )
    return job_id


async def _delete_jobs(*job_ids: uuid.UUID) -> None:
    if not job_ids:
        return
    async with _Session() as session:
        async with session.begin():
            for jid in job_ids:
                await session.execute(
                    text("DELETE FROM public.task_jobs WHERE id = :id"),
                    {"id": str(jid)},
                )


def _mock_task_fn() -> MagicMock:
    fn = MagicMock()
    fn.apply_async = MagicMock()
    return fn


# ---------------------------------------------------------------------------
# Group 1 — Import and app wiring
# ---------------------------------------------------------------------------


async def test_router_registered():
    routes = {
        (frozenset(r.methods), r.path)
        for r in app.routes
        if hasattr(r, "methods") and hasattr(r, "path")
    }
    assert (frozenset({"GET"}),  "/jobs")                 in routes
    assert (frozenset({"GET"}),  "/jobs/{job_id}")        in routes
    assert (frozenset({"POST"}), "/jobs/{job_id}/cancel") in routes
    assert (frozenset({"POST"}), "/jobs")             not in routes


# ---------------------------------------------------------------------------
# Group 2 — Repository (direct DB)
# ---------------------------------------------------------------------------


async def test_repo_create(test_tenant_a):
    async with _Session() as session:
        async with session.begin():
            data = TaskJobCreate(
                task_type="repo.create",
                queue_name="celery",
                tenant_id=test_tenant_a["id"],
            )
            job = await TaskJobRepository.create(data, db=session)
            job_id = job.id

    try:
        assert job_id is not None
        assert job.status == TaskJobStatus.PENDING
        assert job.task_type == "repo.create"
        assert job.tenant_id == test_tenant_a["id"]
        assert job.created_at is not None
    finally:
        await _delete_jobs(job_id)


async def test_repo_get_by_id_found(test_tenant_a):
    job_id = await _insert_job(test_tenant_a["id"], task_type="repo.get")
    try:
        async with _Session() as session:
            job = await TaskJobRepository.get_by_id(
                job_id, tenant_id=test_tenant_a["id"], db=session
            )
        assert job is not None
        assert job.id == job_id
    finally:
        await _delete_jobs(job_id)


async def test_repo_get_by_id_wrong_tenant(test_tenant_a, test_tenant_b):
    job_id = await _insert_job(test_tenant_a["id"])
    try:
        async with _Session() as session:
            result = await TaskJobRepository.get_by_id(
                job_id, tenant_id=test_tenant_b["id"], db=session
            )
        assert result is None
    finally:
        await _delete_jobs(job_id)


async def test_repo_list_filters_status(test_tenant_a):
    pending_id = await _insert_job(test_tenant_a["id"], task_type="repo.filter.st", status="PENDING")
    success_id = await _insert_job(test_tenant_a["id"], task_type="repo.filter.st", status="SUCCESS")
    try:
        async with _Session() as session:
            rows = await TaskJobRepository.list(
                tenant_id=test_tenant_a["id"],
                status=TaskJobStatus.PENDING,
                task_type="repo.filter.st",
                db=session,
            )
        ids = {r.id for r in rows}
        assert pending_id in ids
        assert success_id not in ids
    finally:
        await _delete_jobs(pending_id, success_id)


async def test_repo_list_filters_task_type(test_tenant_a):
    match_id = await _insert_job(test_tenant_a["id"], task_type="repo.filter.tt.match")
    other_id = await _insert_job(test_tenant_a["id"], task_type="repo.filter.tt.other")
    try:
        async with _Session() as session:
            rows = await TaskJobRepository.list(
                tenant_id=test_tenant_a["id"],
                task_type="repo.filter.tt.match",
                db=session,
            )
        ids = {r.id for r in rows}
        assert match_id in ids
        assert other_id not in ids
    finally:
        await _delete_jobs(match_id, other_id)


async def test_repo_list_ordering(test_tenant_a):
    # Explicit created_at offsets ensure deterministic DESC ordering.
    oldest_id = await _insert_job(test_tenant_a["id"], task_type="repo.order", created_at_offset=2)
    middle_id = await _insert_job(test_tenant_a["id"], task_type="repo.order", created_at_offset=1)
    newest_id = await _insert_job(test_tenant_a["id"], task_type="repo.order", created_at_offset=0)
    try:
        async with _Session() as session:
            rows = await TaskJobRepository.list(
                tenant_id=test_tenant_a["id"],
                task_type="repo.order",
                db=session,
            )
        ordered_ids = [r.id for r in rows]
        assert ordered_ids.index(newest_id) < ordered_ids.index(middle_id)
        assert ordered_ids.index(middle_id) < ordered_ids.index(oldest_id)
    finally:
        await _delete_jobs(oldest_id, middle_id, newest_id)


async def test_repo_count(test_tenant_a):
    ids = [
        await _insert_job(test_tenant_a["id"], task_type="repo.count")
        for _ in range(3)
    ]
    try:
        async with _Session() as session:
            n = await TaskJobRepository.count(
                tenant_id=test_tenant_a["id"],
                task_type="repo.count",
                db=session,
            )
            rows = await TaskJobRepository.list(
                tenant_id=test_tenant_a["id"],
                task_type="repo.count",
                db=session,
            )
        assert n == len(rows) == 3
    finally:
        await _delete_jobs(*ids)


async def test_repo_cancel_pending(test_tenant_a):
    job_id = await _insert_job(test_tenant_a["id"], status="PENDING")
    try:
        async with _Session() as session:
            async with session.begin():
                job = await TaskJobRepository.cancel(
                    job_id, tenant_id=test_tenant_a["id"], db=session
                )
        assert job is not None
        assert job.status == TaskJobStatus.CANCELLED
        assert job.completed_at is not None
    finally:
        await _delete_jobs(job_id)


async def test_repo_cancel_terminal(test_tenant_a):
    job_id = await _insert_job(test_tenant_a["id"], status="SUCCESS")
    try:
        async with _Session() as session:
            async with session.begin():
                result = await TaskJobRepository.cancel(
                    job_id, tenant_id=test_tenant_a["id"], db=session
                )
        assert result is None
    finally:
        await _delete_jobs(job_id)


async def test_repo_cancel_wrong_tenant(test_tenant_a, test_tenant_b):
    job_id = await _insert_job(test_tenant_a["id"], status="PENDING")
    try:
        async with _Session() as session:
            async with session.begin():
                result = await TaskJobRepository.cancel(
                    job_id, tenant_id=test_tenant_b["id"], db=session
                )
        assert result is None
    finally:
        await _delete_jobs(job_id)


# ---------------------------------------------------------------------------
# Group 3 — Service layer
# ---------------------------------------------------------------------------


async def test_service_submit_creates_pending_row(test_tenant_a):
    data = TaskJobCreate(task_type="svc.submit", tenant_id=test_tenant_a["id"])
    task_fn = _mock_task_fn()
    async with _Session() as session:
        response = await TaskQueueService.submit(data, task_fn=task_fn, db=session)
    try:
        assert response.id is not None
        assert response.status == TaskJobStatus.PENDING
        assert response.task_type == "svc.submit"
    finally:
        await _delete_jobs(response.id)


async def test_service_submit_injects_job_id_kwarg(test_tenant_a):
    data = TaskJobCreate(task_type="svc.dispatch", tenant_id=test_tenant_a["id"])
    task_fn = _mock_task_fn()
    async with _Session() as session:
        response = await TaskQueueService.submit(data, task_fn=task_fn, db=session)
    try:
        task_fn.apply_async.assert_called_once()
        call_kwargs = task_fn.apply_async.call_args.kwargs["kwargs"]
        assert call_kwargs["job_id"] == str(response.id)
    finally:
        await _delete_jobs(response.id)


async def test_service_submit_extra_kwargs_forwarded(test_tenant_a):
    data = TaskJobCreate(task_type="svc.extra", tenant_id=test_tenant_a["id"])
    task_fn = _mock_task_fn()
    async with _Session() as session:
        response = await TaskQueueService.submit(
            data, task_fn=task_fn, extra_kwargs={"course_id": "abc"}, db=session
        )
    try:
        call_kwargs = task_fn.apply_async.call_args.kwargs["kwargs"]
        assert call_kwargs["course_id"] == "abc"
        assert "job_id" in call_kwargs
    finally:
        await _delete_jobs(response.id)


async def test_service_submit_dispatch_failure_leaves_pending(test_tenant_a):
    data = TaskJobCreate(task_type="svc.fail_dispatch", tenant_id=test_tenant_a["id"])
    task_fn = _mock_task_fn()
    task_fn.apply_async.side_effect = ConnectionError("Redis unavailable")
    async with _Session() as session:
        # Must not raise even though apply_async failed
        response = await TaskQueueService.submit(data, task_fn=task_fn, db=session)
    try:
        assert response.status == TaskJobStatus.PENDING
    finally:
        await _delete_jobs(response.id)


async def test_service_get_found(test_tenant_a):
    job_id = await _insert_job(test_tenant_a["id"])
    try:
        async with _Session() as session:
            response = await TaskQueueService.get(
                job_id, tenant_id=test_tenant_a["id"], db=session
            )
        assert response.id == job_id
    finally:
        await _delete_jobs(job_id)


async def test_service_get_not_found(test_tenant_a):
    async with _Session() as session:
        with pytest.raises(TaskQueueError) as exc_info:
            await TaskQueueService.get(uuid.uuid4(), tenant_id=test_tenant_a["id"], db=session)
    assert exc_info.value.status_code == 404


async def test_service_get_wrong_tenant_isolation(test_tenant_a, test_tenant_b):
    job_id = await _insert_job(test_tenant_a["id"])
    try:
        async with _Session() as session:
            with pytest.raises(TaskQueueError) as exc_info:
                await TaskQueueService.get(
                    job_id, tenant_id=test_tenant_b["id"], db=session
                )
        assert exc_info.value.status_code == 404
    finally:
        await _delete_jobs(job_id)


async def test_service_cancel_pending(test_tenant_a):
    job_id = await _insert_job(test_tenant_a["id"], status="PENDING")
    try:
        async with _Session() as session:
            response = await TaskQueueService.cancel(
                job_id, tenant_id=test_tenant_a["id"], db=session
            )
        assert response.status == TaskJobStatus.CANCELLED
    finally:
        await _delete_jobs(job_id)


async def test_service_cancel_terminal_409(test_tenant_a):
    job_id = await _insert_job(test_tenant_a["id"], status="FAILED")
    try:
        async with _Session() as session:
            with pytest.raises(TaskQueueError) as exc_info:
                await TaskQueueService.cancel(
                    job_id, tenant_id=test_tenant_a["id"], db=session
                )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "NOT_CANCELLABLE"
    finally:
        await _delete_jobs(job_id)


async def test_service_query_admin_scoped(test_tenant_a, test_tenant_b):
    a_id = await _insert_job(test_tenant_a["id"], task_type="svc.query.scope")
    b_id = await _insert_job(test_tenant_b["id"], task_type="svc.query.scope")
    try:
        async with _Session() as session:
            result = await TaskQueueService.query(
                current_role="ADMIN",
                current_tenant_id=test_tenant_a["id"],
                task_type="svc.query.scope",
                db=session,
            )
        ids = {item.id for item in result.items}
        assert a_id in ids
        assert b_id not in ids
    finally:
        await _delete_jobs(a_id, b_id)


async def test_service_query_super_admin_sees_all(test_tenant_a, test_tenant_b):
    a_id = await _insert_job(test_tenant_a["id"], task_type="svc.query.super")
    b_id = await _insert_job(test_tenant_b["id"], task_type="svc.query.super")
    try:
        async with _Session() as session:
            result = await TaskQueueService.query(
                current_role="SUPER_ADMIN",
                current_tenant_id=None,
                task_type="svc.query.super",
                db=session,
            )
        ids = {item.id for item in result.items}
        assert a_id in ids
        assert b_id in ids
    finally:
        await _delete_jobs(a_id, b_id)


# ---------------------------------------------------------------------------
# Group 4 — Router / HTTP endpoints
# ---------------------------------------------------------------------------

# --- Unauthenticated / RBAC ---


async def test_list_unauthenticated(async_client):
    resp = await async_client.get("/jobs")
    # Missing Authorization header → 422 from FastAPI header validation;
    # invalid token → 401 from get_current_user. Both reject the request.
    assert resp.status_code in (401, 422)


async def test_get_unauthenticated(async_client):
    resp = await async_client.get(f"/jobs/{uuid.uuid4()}")
    assert resp.status_code in (401, 422)


async def test_cancel_unauthenticated(async_client):
    resp = await async_client.post(f"/jobs/{uuid.uuid4()}/cancel")
    assert resp.status_code in (401, 422)


async def test_list_faculty_forbidden(async_client, test_tenant_a, faculty_user_a):
    resp = await async_client.get("/jobs", headers=make_tenant_headers(faculty_user_a))
    assert resp.status_code == 403


# --- Invalid query param ---


async def test_invalid_status_filter_returns_422(async_client, test_tenant_a, admin_user_a):
    resp = await async_client.get(
        "/jobs",
        params={"status": "INVALID_STATUS"},
        headers=make_tenant_headers(admin_user_a),
    )
    assert resp.status_code == 422


# --- List / pagination / filtering ---


async def test_list_admin_scoped(async_client, test_tenant_a, test_tenant_b, admin_user_a):
    a_id = await _insert_job(test_tenant_a["id"], task_type="router.scope")
    b_id = await _insert_job(test_tenant_b["id"], task_type="router.scope")
    try:
        resp = await async_client.get(
            "/jobs",
            params={"task_type": "router.scope"},
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert str(a_id) in ids
        assert str(b_id) not in ids
    finally:
        await _delete_jobs(a_id, b_id)


async def test_list_super_admin_sees_all(
    async_client, test_tenant_a, test_tenant_b, test_platform_user
):
    a_id = await _insert_job(test_tenant_a["id"], task_type="router.super.scope")
    b_id = await _insert_job(test_tenant_b["id"], task_type="router.super.scope")
    try:
        resp = await async_client.get(
            "/jobs",
            params={"task_type": "router.super.scope"},
            headers=make_platform_headers(test_platform_user),
        )
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert str(a_id) in ids
        assert str(b_id) in ids
    finally:
        await _delete_jobs(a_id, b_id)


async def test_list_filter_status(async_client, test_tenant_a, admin_user_a):
    pending_id = await _insert_job(test_tenant_a["id"], task_type="router.filter", status="PENDING")
    success_id = await _insert_job(test_tenant_a["id"], task_type="router.filter", status="SUCCESS")
    try:
        resp = await async_client.get(
            "/jobs",
            params={"task_type": "router.filter", "status": "PENDING"},
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["items"]}
        assert str(pending_id) in ids
        assert str(success_id) not in ids
    finally:
        await _delete_jobs(pending_id, success_id)


async def test_list_pagination(async_client, test_tenant_a, admin_user_a):
    # Insert 5 rows with distinct created_at so ordering is deterministic
    ids = [
        await _insert_job(
            test_tenant_a["id"],
            task_type="router.page",
            created_at_offset=i,
        )
        for i in range(5, 0, -1)
    ]
    try:
        page1 = await async_client.get(
            "/jobs",
            params={"task_type": "router.page", "page": 1, "page_size": 3},
            headers=make_tenant_headers(admin_user_a),
        )
        page2 = await async_client.get(
            "/jobs",
            params={"task_type": "router.page", "page": 2, "page_size": 3},
            headers=make_tenant_headers(admin_user_a),
        )
        assert page1.status_code == 200
        assert page2.status_code == 200
        p1 = page1.json()
        p2 = page2.json()
        assert p1["total"] >= 5
        assert len(p1["items"]) == 3
        assert len(p2["items"]) >= 1
        assert {i["id"] for i in p1["items"]}.isdisjoint({i["id"] for i in p2["items"]})
    finally:
        await _delete_jobs(*ids)


# --- Get single job ---


async def test_get_admin_own_tenant(async_client, test_tenant_a, admin_user_a):
    job_id = await _insert_job(test_tenant_a["id"])
    try:
        resp = await async_client.get(
            f"/jobs/{job_id}",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(job_id)
    finally:
        await _delete_jobs(job_id)


async def test_get_admin_other_tenant(async_client, test_tenant_a, test_tenant_b, admin_user_a):
    job_id = await _insert_job(test_tenant_b["id"])
    try:
        resp = await async_client.get(
            f"/jobs/{job_id}",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 404
    finally:
        await _delete_jobs(job_id)


async def test_get_super_admin_any_tenant(async_client, test_tenant_b, test_platform_user):
    job_id = await _insert_job(test_tenant_b["id"])
    try:
        resp = await async_client.get(
            f"/jobs/{job_id}",
            headers=make_platform_headers(test_platform_user),
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(job_id)
    finally:
        await _delete_jobs(job_id)


async def test_get_job_not_found(async_client, test_platform_user):
    resp = await async_client.get(
        f"/jobs/{uuid.uuid4()}",
        headers=make_platform_headers(test_platform_user),
    )
    assert resp.status_code == 404


# --- Cancel ---


async def test_cancel_pending_success(async_client, test_tenant_a, admin_user_a):
    job_id = await _insert_job(test_tenant_a["id"], status="PENDING")
    try:
        resp = await async_client.post(
            f"/jobs/{job_id}/cancel",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "CANCELLED"
        assert body["completed_at"] is not None
    finally:
        await _delete_jobs(job_id)


async def test_cancel_terminal_conflict(async_client, test_tenant_a, admin_user_a):
    job_id = await _insert_job(test_tenant_a["id"], status="SUCCESS")
    try:
        resp = await async_client.post(
            f"/jobs/{job_id}/cancel",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 409
        # http_exception_handler in main.py unwraps detail dicts directly,
        # so the response body is {"error": ..., "message": ...} not {"detail": ...}.
        assert resp.json()["error"] == "NOT_CANCELLABLE"
    finally:
        await _delete_jobs(job_id)


async def test_cancel_admin_other_tenant(async_client, test_tenant_a, test_tenant_b, admin_user_a):
    job_id = await _insert_job(test_tenant_b["id"], status="PENDING")
    try:
        resp = await async_client.post(
            f"/jobs/{job_id}/cancel",
            headers=make_tenant_headers(admin_user_a),
        )
        assert resp.status_code == 409
    finally:
        await _delete_jobs(job_id)


async def test_cancel_super_admin_any_tenant(async_client, test_tenant_b, test_platform_user):
    job_id = await _insert_job(test_tenant_b["id"], status="PENDING")
    try:
        resp = await async_client.post(
            f"/jobs/{job_id}/cancel",
            headers=make_platform_headers(test_platform_user),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "CANCELLED"
    finally:
        await _delete_jobs(job_id)
